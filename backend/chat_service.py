"""Chat orchestration for the OpenUI frontend.

One request flows through:

    guardrails -> Jev routing (LangChain classifier as fallback)
      -> database: LangChain query generation -> validator -> MongoDB tool
      -> general:  configured LLM (optional Graphiti context)
    -> OpenUI Lang generation -> line sanitizer -> grounding check
    -> AG-UI server-sent events -> OpenUI renderer in the browser

Events follow the AG-UI protocol consumed by ``agUIAdapter`` in
``@openuidev/react-headless``. Routing and the MongoDB query are emitted as
tool calls so the OpenUI interface shows them in its tool timeline.
"""

import asyncio
import json
import time
import uuid

from backend import account, artifacts, langchain_agent
from backend.analytics import answer_analysis
from backend.config import settings
from backend.geo import build_geo_payload
from backend.guardrails import GuardrailViolation, check_question
from backend.insights import result_insights
from backend.jev_router import interpret_route, route_question
from backend.observability import finish_trace, logger, record_span, start_trace
from backend.openui_validator import validate as validate_openui
from backend.openui_engine import (
    LineSanitizer,
    OpenUIUnavailable,
    data_messages,
    fallback_data_ui,
    fallback_message_ui,
    general_messages,
    grounding_issues,
    repair_messages,
    stream_openui,
    wrap_prose,
)
from backend.schema_discovery import get_schema
from backend.threads import message_text, save_messages

def model_options():
    """Models the user may pick in the OpenUI ModelSwitcher (OpenRouter ids)."""

    options = list(settings.openui_model_options)
    if settings.openui_model not in options:
        options.insert(0, settings.openui_model)
    return options


# Validated queries for recently asked questions. A repeat question skips
# the query-generation LLM call (the slowest step); the query still runs
# against MongoDB, so results are always current.
QUERY_CACHE_TTL_SECONDS = 900
QUERY_CACHE_SIZE = 256
_QUERY_CACHE = {}


def _cached_query(key):
    entry = _QUERY_CACHE.get(key)
    if entry is None:
        return None
    query, stored_at = entry
    if time.monotonic() - stored_at > QUERY_CACHE_TTL_SECONDS:
        _QUERY_CACHE.pop(key, None)
        return None
    return query


def _remember_query(key, query):
    if len(_QUERY_CACHE) >= QUERY_CACHE_SIZE:
        _QUERY_CACHE.pop(next(iter(_QUERY_CACHE)))
    _QUERY_CACHE[key] = (query, time.monotonic())


async def with_heartbeat(events, interval=10.0):
    """Interleave SSE comment lines while a slow stage runs.

    Proxies (including the Next.js rewrite) close connections that stay
    silent too long; ``: keep-alive`` comments keep the stream open and are
    ignored by OpenUI's agUIAdapter, which only reads ``data:`` lines.
    """

    queue = asyncio.Queue()
    finished = object()

    async def pump():
        try:
            async for item in events:
                await queue.put(item)
        finally:
            await queue.put(finished)

    task = asyncio.create_task(pump())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), interval)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if item is finished:
                break
            yield item
    finally:
        task.cancel()


def sse(event):
    return f"data: {json.dumps(event, default=str, ensure_ascii=False)}\n\n"


def _history(messages):
    """Text history for the LLM, excluding the current user message."""

    history = []
    for message in messages[:-1]:
        role = message.get("role")
        text = message_text(message)
        if role in {"user", "assistant"} and text:
            history.append({"role": role, "content": text})
    return history


def _contextual_question(question, history):
    """Give query generation the earlier questions so follow-ups resolve."""

    earlier = [item["content"] for item in history if item["role"] == "user"][-3:]
    if not earlier:
        return question
    context = "; ".join(q[:200] for q in earlier)
    return f"{question}\n\n(Earlier questions in this conversation, for context only: {context})"


class ChatRun:
    def __init__(self, user, thread_id, messages, model=None):
        self.user = user
        self.thread_id = thread_id
        self.run_id = str(uuid.uuid4())
        self.messages = messages
        self.model = model if model in model_options() else None
        self.generated = []
        # (tool name, args, result) of every tool call, saved as artifacts.
        self.tool_results = []
        self.question = message_text(messages[-1]) if messages else ""
        self.trace = None
        self.text_message_id = None
        self.text_open = False
        self.text_parts = []

    # ---------------- event helpers ----------------

    def tool_events(self, name, args, result):
        call_id = f"call_{uuid.uuid4().hex[:12]}"
        args_text = json.dumps(args, default=str, ensure_ascii=False)
        result_text = json.dumps(result, default=str, ensure_ascii=False)
        self.tool_results.append((name, args, result))

        self.generated.append(
            {
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": "",
                "toolCalls": [
                    {"id": call_id, "type": "function", "function": {"name": name, "arguments": args_text}}
                ],
            }
        )
        self.generated.append(
            {"id": str(uuid.uuid4()), "role": "tool", "toolCallId": call_id, "content": result_text}
        )

        return [
            sse({"type": "TOOL_CALL_START", "toolCallId": call_id, "toolCallName": name}),
            sse({"type": "TOOL_CALL_ARGS", "toolCallId": call_id, "delta": args_text}),
            sse({"type": "TOOL_CALL_END", "toolCallId": call_id}),
            sse(
                {
                    "type": "TOOL_CALL_RESULT",
                    "messageId": str(uuid.uuid4()),
                    "toolCallId": call_id,
                    "role": "tool",
                    "content": result_text,
                }
            ),
        ]

    def text_start(self):
        self.text_message_id = str(uuid.uuid4())
        self.text_parts = []
        self.text_open = True
        return sse({"type": "TEXT_MESSAGE_START", "messageId": self.text_message_id, "role": "assistant"})

    def text(self, delta):
        if not delta:
            return ""
        self.text_parts.append(delta)
        return sse({"type": "TEXT_MESSAGE_CONTENT", "messageId": self.text_message_id, "delta": delta})

    def text_end(self):
        self.text_open = False
        self.generated.append(
            {"id": self.text_message_id, "role": "assistant", "content": "".join(self.text_parts)}
        )
        return sse({"type": "TEXT_MESSAGE_END", "messageId": self.text_message_id})

    def answer_meta(self):
        """How each answer text was produced, for feedback analysis."""

        info = {
            "trace_id": self.trace.id if self.trace else None,
            "route": self.trace.route if self.trace else None,
            "status": self.trace.status if self.trace else None,
            "model": self.model or settings.openui_model,
        }
        return {
            message["id"]: info
            for message in self.generated
            if message["role"] == "assistant" and not message.get("toolCalls")
        }

    # ---------------- main flow ----------------

    async def events(self):
        self.trace = start_trace(self.user["username"], self.question, self.thread_id)
        yield sse({"type": "RUN_STARTED", "threadId": self.thread_id, "runId": self.run_id})

        try:
            async for event in self._answer():
                yield event
        except Exception as error:  # noqa: BLE001 - last-resort safety net
            logger.exception("chat run failed")
            self.trace.status = "error"
            self.trace.error = type(error).__name__
            if not self.text_open:
                yield self.text_start()
            yield self.text(
                "\n" + fallback_message_ui(
                    "Something went wrong",
                    "The request could not be completed. Please try again.",
                    "error",
                )
            )
            yield self.text_end()
        finally:
            if self.thread_id:
                try:
                    await asyncio.to_thread(
                        save_messages,
                        self.thread_id,
                        self.user["username"],
                        list(self.messages) + self.generated,
                        self.answer_meta(),
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("could not save thread")
                try:
                    await asyncio.to_thread(
                        artifacts.save_run_artifacts,
                        self.user["username"],
                        self.thread_id,
                        self.question,
                        self.tool_results,
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("could not save artifacts")
            summary = finish_trace(self.trace)
            try:
                await asyncio.to_thread(
                    account.record_usage,
                    self.user["username"],
                    summary.get("total_tokens") or 0,
                    summary.get("cost_usd") or 0.0,
                )
            except Exception:  # noqa: BLE001
                logger.warning("could not record usage", exc_info=True)

        yield sse({"type": "RUN_FINISHED", "threadId": self.thread_id, "runId": self.run_id})

    async def _answer(self):
        try:
            await asyncio.to_thread(account.count_message, self.user)
        except account.QuotaExceeded as limit:
            self.trace.route = "blocked"
            self.trace.status = "blocked:quota"
            yield self.text_start()
            yield self.text(fallback_message_ui("Daily limit reached", limit.message, "warning"))
            yield self.text_end()
            return
        except Exception:  # noqa: BLE001 - usage tracking must never block an answer
            logger.warning("usage tracking skipped", exc_info=True)

        try:
            question = check_question(self.question)
        except GuardrailViolation as violation:
            self.trace.route = "blocked"
            self.trace.status = f"blocked:{violation.code}"
            yield self.text_start()
            yield self.text(fallback_message_ui("Request not processed", violation.message, "warning"))
            yield self.text_end()
            return

        history = _history(self.messages)

        route, route_info = await self.route(question)
        self.trace.route = route
        for event in self.tool_events("route_question", {"question": question}, route_info):
            yield event

        if route == "database_query":
            async for event in self.database_answer(question, history):
                yield event
        else:
            async for event in self.general_answer(question, history, browser=route == "browser_task"):
                yield event

    async def route(self, question):
        """Jev first; LangChain classifier when Jev is unsure or unavailable."""

        try:
            schema = await asyncio.to_thread(get_schema)
        except Exception as error:  # MongoDB unavailable
            logger.warning("schema discovery failed: %s", error)
            schema = None

        if settings.jev_enabled and settings.openrouter_api_key:
            started = time.perf_counter()
            try:
                result = await asyncio.to_thread(route_question, question, schema)
                route, confidence, cost = interpret_route(result)
                record_span("jev routing", time.perf_counter() - started, kind="llm",
                            model=settings.jev_model, cost=cost,
                            input_tokens=result.get("usage", {}).get("input_tokens"),
                            output_tokens=result.get("usage", {}).get("output_tokens"))
                if route and confidence >= settings.jev_min_confidence:
                    if route == "database_query" and not schema:
                        return "general_chat", {"route": "general_chat", "source": "jev",
                                                "note": "database unavailable"}
                    self.trace.route_source = "jev"
                    return route, {"route": route, "confidence": confidence, "source": "jev"}
                jev_note = {"jev_route": route, "jev_confidence": confidence}
            except Exception as error:  # noqa: BLE001
                record_span("jev routing failed", time.perf_counter() - started)
                logger.warning("Jev routing failed: %s", error)
                jev_note = {"jev_error": type(error).__name__}
        else:
            jev_note = {"jev": "disabled"}

        if not schema:
            self.trace.route_source = "no-database"
            return "general_chat", {"route": "general_chat", "source": "no-database", **jev_note}

        try:
            is_db = await asyncio.to_thread(langchain_agent.is_database_question, question)
            route = "database_query" if is_db else "general_chat"
            self.trace.route_source = "langchain"
            return route, {"route": route, "source": "langchain-classifier", **jev_note}
        except Exception as error:  # noqa: BLE001
            logger.warning("LangChain routing failed: %s", error)
            self.trace.route_source = "default"
            return "general_chat", {"route": "general_chat", "source": "default", **jev_note}

    async def database_answer(self, question, history):
        query_question = _contextual_question(question, history)
        query, result, repair = None, None, None
        started = time.perf_counter()

        cache_key = " ".join(query_question.lower().split())
        cached = _cached_query(cache_key)
        if cached is not None:
            try:
                result = await asyncio.to_thread(langchain_agent.execute_mongodb_query, cached)
                query = cached
            except Exception:  # noqa: BLE001 - schema changed; regenerate below
                _QUERY_CACHE.pop(cache_key, None)
                result = None

        for attempt in range(0 if result is not None else 2):
            try:
                query = await asyncio.to_thread(
                    langchain_agent.generate_database_query, query_question, repair
                )
            except Exception as error:  # noqa: BLE001
                repair = f"Query generation exception: {error}"
                query = None
                continue
            if not query:
                repair = "The model did not return a valid JSON query."
                continue
            try:
                result = await asyncio.to_thread(langchain_agent.execute_mongodb_query, query)
                _remember_query(cache_key, query)
                break
            except Exception as error:  # noqa: BLE001 - validator or DB error
                repair = (
                    f"Previous query:\n{json.dumps(query, default=str)}\n\n"
                    f"Actual database or validation error:\n{error}"
                )
                result = None

        latency = time.perf_counter() - started
        record_span("mongodb tool", latency, kind="tool", ok=result is not None)

        if result is None or not isinstance(result, list):
            self.trace.status = "query_failed"
            for event in self.tool_events(
                "query_mongodb",
                query or {"question": question},
                {"ok": False, "error": "The query could not be generated or did not pass validation."},
            ):
                yield event
            yield self.text_start()
            yield self.text(
                fallback_message_ui(
                    "I couldn't answer this from the database",
                    "No validated query produced a result, so I won't guess. "
                    "Try rephrasing the question or naming the collection or field.",
                    "warning",
                )
            )
            yield self.text_end()
            return

        truncated = len(result) >= settings.max_result_rows
        for event in self.tool_events(
            "query_mongodb",
            query,
            {
                "ok": True,
                "rows_returned": len(result),
                "truncated": truncated,
                "latency_ms": round(latency * 1000),
                "preview": result[:25],
            },
        ):
            yield event

        for event in self.analysis_events(question, rows=result, query=query):
            yield event

        yield self.text_start()

        follow_ups = None
        simple = query.get("operation") in {"count", "distinct"} or not result
        if simple:
            # A count or an empty result needs no extra model call.
            yield self.text(
                fallback_data_ui(question, query, result, follow_ups=follow_ups)
            )
            yield self.text_end()
            return

        async for event in self.stream_ui(
            data_messages(question, query, result, history, truncated),
            "openui data answer",
            data=result,
            question=question,
        ):
            yield event

        if self.ui_problem:
            self.trace.fallback_used = True
            note = (
                "Showing the verified result because the answer generator was unavailable."
                if self.ui_problem == "unavailable"
                else "The generated view did not pass validation, so the verified result is shown instead."
            )
            yield self.text("\n" + fallback_data_ui(question, query, result, note=note))

        yield self.text_end()

    async def general_answer(self, question, history, browser=False):
        context = await self.graphiti_context(question)
        yield self.text_start()

        async for event in self.stream_ui(
            general_messages(question, history, context, browser),
            "openui general answer",
        ):
            yield event

        if self.ui_problem == "unavailable":
            self.trace.fallback_used = True
            self.trace.status = "provider_unavailable"
            yield self.text(
                "\n" + fallback_message_ui(
                    "The language model is unavailable",
                    "General questions need the configured LLM provider. Data questions "
                    "still work when MongoDB is running. Check OPENROUTER_API_KEY.",
                    "warning",
                )
            )
        elif self.ui_problem and not self.ui_has_root:
            self.trace.fallback_used = True
            if self.ui_prose:
                yield self.text("\n" + wrap_prose(self.ui_prose))
            else:
                yield self.text(
                    "\n" + fallback_message_ui(
                        "No answer was produced",
                        "The model returned an empty or invalid response. Please try again.",
                        "warning",
                    )
                )
        # A general answer with a root but minor schema errors is kept: the
        # OpenUI renderer drops only the invalid components.
        answer_text = "".join(self.text_parts)
        yield self.text_end()

        if not self.ui_problem or self.ui_has_root:
            for event in self.analysis_events(question, answer_text=answer_text):
                yield event

    def analysis_events(self, question, rows=None, answer_text=None, query=None):
        """Geographic map and visual analysis, emitted as tool calls.

        Both are computed from the verified MongoDB rows (or the places named
        in the question/answer) with no extra LLM call. ``visual_analysis``
        covers every database answer (counts, lists, distinct values, groups);
        ``data_insights`` remains the fallback when it has nothing to show.
        A failure here never affects the answer itself.
        """

        events = []
        started = time.perf_counter()
        try:
            geo = build_geo_payload(question, rows, answer_text)
            if geo:
                events += self.tool_events("geo_map", {"question": question, "source": geo["source"]}, geo)
            visual = answer_analysis(query, rows) if rows and query else None
            insights = None if visual else (result_insights(rows) if rows else None)
            if visual:
                events += self.tool_events("visual_analysis", {"question": question}, visual)
            elif insights:
                events += self.tool_events("data_insights", {"question": question}, insights)
        except Exception:  # noqa: BLE001 - optional enrichment
            logger.exception("geo/insight analysis failed")
        record_span("geo and insights", time.perf_counter() - started, kind="check", events=len(events) // 4)
        return events

    # ---------------- OpenUI generation with validation ----------------

    async def problems_in(self, sanitizer, data=None, question=""):
        problems = []
        started = time.perf_counter()
        if not sanitizer.has_root:
            problems.append("The program must start with root = Card([...]).")
        verdict = await asyncio.to_thread(validate_openui, sanitizer.text)
        if verdict is not None:
            problems.extend(verdict.get("errors", []))
            if verdict.get("unresolved"):
                problems.append("Undefined references: " + ", ".join(verdict["unresolved"]))
        if data is not None:
            issues = grounding_issues(sanitizer.text, data, question)
            if issues:
                problems.append(
                    "These numbers are not in the DATABASE RESULT and must be removed or "
                    "corrected: " + ", ".join(f"{n:g}" for n in issues[:10])
                )
        record_span(
            "openui validation", time.perf_counter() - started, kind="check",
            parser="official" if verdict is not None else "unavailable",
            dropped_lines=len(sanitizer.dropped), autofixed=sanitizer.autofixed, problems=problems[:5],
        )
        return problems

    async def stream_ui(self, messages, stage, data=None, question=""):
        """Stream OpenUI Lang, validate it, and repair it once if needed.

        Sets ``self.ui_problem`` to None (valid), "unavailable" or "invalid".
        """

        self.ui_problem, self.ui_has_root, self.ui_prose = None, False, []
        sanitizer = LineSanitizer()
        try:
            async for chunk in stream_openui(messages, self.model, stage):
                yield self.text(sanitizer.feed(chunk))
            yield self.text(sanitizer.finish())
        except OpenUIUnavailable as error:
            logger.warning("OpenUI generation unavailable: %s", error)
            self.ui_problem = "unavailable"
            return

        self.ui_has_root, self.ui_prose = sanitizer.has_root, sanitizer.prose
        problems = await self.problems_in(sanitizer, data, question)
        if not problems:
            return

        # One repair pass, like OpenUI Autofix: give the model the exact
        # parser errors and ask for a corrected full program.
        repaired = LineSanitizer()
        try:
            async for chunk in stream_openui(
                repair_messages(sanitizer.text or "\n".join(sanitizer.prose), problems, messages),
                self.model,
                f"{stage} repair",
            ):
                repaired.feed(chunk)
            repaired.finish()
        except OpenUIUnavailable:
            self.ui_problem = "invalid"
            return

        if repaired.has_root and not await self.problems_in(repaired, data, question):
            self.trace.repaired = True
            # A later `root = ...` replaces the earlier one in the parser.
            yield self.text("\n" + repaired.text + "\n")
            self.ui_has_root = True
            return

        self.ui_problem = "invalid"

    async def graphiti_context(self, question):
        if not settings.graphiti_enabled:
            return None
        started = time.perf_counter()
        try:
            from backend.graphiti_context import search_context

            context = await asyncio.wait_for(search_context(question), timeout=8)
            record_span("graphiti context", time.perf_counter() - started, kind="tool", ok=True)
            return context
        except Exception as error:  # noqa: BLE001 - optional service
            record_span("graphiti context", time.perf_counter() - started, kind="tool", ok=False)
            logger.warning("Graphiti context unavailable: %s", error)
            return None
