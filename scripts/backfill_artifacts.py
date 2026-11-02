"""Create Artifacts-library entries for conversations saved before artifacts existed.

Reads every stored conversation (chat_threads), pairs each tool call with its
tool result, and saves the charts, maps, insights and queries as artifacts,
exactly as backend/chat_service.py does for new answers. Threads that already
have artifacts are skipped, so the script is safe to run again.

    python -m scripts.backfill_artifacts            # all users
    python -m scripts.backfill_artifacts --dry-run  # only report what it would do
"""

import argparse
import json

from backend import artifacts
from backend.threads import message_text, threads


def _json(value):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "null")
    except (TypeError, ValueError):
        return None


def runs(messages):
    """Yield (question, [(tool, args, result), ...]) for each user turn."""

    question, calls, pending = "", [], {}
    for message in messages:
        role = message.get("role")
        if role == "user":
            if calls:
                yield question, calls
            question, calls, pending = message_text(message), [], {}
        elif role == "assistant":
            for call in message.get("toolCalls") or []:
                function = call.get("function") or {}
                pending[call.get("id")] = (function.get("name"), _json(function.get("arguments")) or {})
        elif role == "tool" and message.get("toolCallId") in pending:
            name, args = pending.pop(message["toolCallId"])
            result = _json(message.get("content"))
            if isinstance(result, dict):
                calls.append((name, args, result))
    if calls:
        yield question, calls


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    options = parser.parse_args()

    artifacts.ensure_indexes()
    done = set(artifacts.artifacts.distinct("threadId"))
    scanned = created = 0
    for thread in threads.find({}, {"username": 1, "messages": 1}):
        scanned += 1
        if thread["_id"] in done:
            continue
        for question, calls in runs(thread.get("messages") or []):
            docs = artifacts.build_artifacts(thread["username"], thread["_id"], question, calls)
            if docs and not options.dry_run:
                artifacts.artifacts.insert_many(docs)
            created += len(docs)
    verb = "would create" if options.dry_run else "created"
    print(f"Scanned {scanned} conversations; {verb} {created} artifacts.")


if __name__ == "__main__":
    main()
