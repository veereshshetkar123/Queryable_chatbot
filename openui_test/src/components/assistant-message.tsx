"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BarChart3, ChevronRight, LayoutPanelLeft, PanelRightClose, ThumbsDown, ThumbsUp } from "lucide-react";
import { create } from "zustand";
import {
  DetailedViewPanel,
  useDetailedView,
  useThread,
  useThreadList,
  type AssistantMessage,
} from "@openuidev/react-ui";
import { openuiChatLibrary } from "@openuidev/react-ui/genui-lib";
import { BuiltinActionType, Renderer, type ActionEvent } from "@openuidev/react-lang";

import { authFetch, errorMessage } from "@/lib/api";

/**
 * Assistant message = OpenUI's GenUI rendering + a thumbs up / down bar.
 *
 * AgentInterface's `components.AssistantMessage` replaces the whole message
 * and the built-in GenUIAssistantMessage is not exported, so the rendering
 * half below mirrors it (@openuidev/react-ui 0.16.3): same Renderer, same
 * form-state persistence and the same action handling.
 */

// OpenUI's inline section markers (react-ui src/utils/sentinelParser.ts).
// The backend never writes them; they appear once a form in an answer
// stores its state into the message.
const CONTENT_MARKER = "]]>openui:content";
const CONTEXT_MARKER = "]]>openui:context";
const END_MARKER = "]]>openui:end";

function afterHeader(raw: string, index: number) {
  const lineEnd = raw.indexOf("\n", index);
  return lineEnd === -1 ? raw.length : lineEnd + 1;
}

function trimNewline(value: string) {
  return value.replace(/\r?\n$/, "");
}

function splitMessage(raw: string): { content: string; context: string | null; header?: string } {
  const text = raw
    .split("\n")
    .filter((line) => !line.startsWith(END_MARKER))
    .join("\n");
  const contentAt = text.lastIndexOf(CONTENT_MARKER);
  const contextAt = text.lastIndexOf(CONTEXT_MARKER);

  if (contentAt === -1 && contextAt === -1) return { content: text, context: null };
  if (contentAt === -1) {
    return { content: trimNewline(text.slice(0, contextAt)), context: text.slice(afterHeader(text, contextAt)) };
  }
  const header = text.slice(contentAt, afterHeader(text, contentAt)).replace(/\n$/, "");
  if (contextAt === -1 || contentAt > contextAt) {
    return { content: text.slice(afterHeader(text, contentAt)), context: null, header };
  }
  return {
    content: trimNewline(text.slice(afterHeader(text, contentAt), contextAt)),
    context: text.slice(afterHeader(text, contextAt)),
    header,
  };
}

function parseState(context: string | null): Record<string, unknown> | undefined {
  if (!context) return undefined;
  try {
    const parsed: unknown = JSON.parse(context);
    if (Array.isArray(parsed) && parsed[0] && typeof parsed[0] === "object") return parsed[0] as Record<string, unknown>;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed as Record<string, unknown>;
  } catch {
    // A partly streamed or hand-edited context is ignored, as OpenUI does.
  }
  return undefined;
}

// ------------------------------------------------------------------
// Feedback state, one request per conversation
// ------------------------------------------------------------------

type Rating = { rating: "up" | "down"; reasons: string[]; comment: string };

// Must match REASONS in backend/feedback.py.
const REASONS = [
  { id: "wrong_numbers", label: "Wrong numbers" },
  { id: "off_topic", label: "Didn't answer my question" },
  { id: "incomplete", label: "Missing information" },
  { id: "hard_to_read", label: "Hard to read" },
  { id: "slow", label: "Too slow" },
  { id: "other", label: "Other" },
];

type FeedbackStore = {
  ratings: Record<string, Rating | undefined>;
  loaded: Record<string, boolean>;
  load: (threadId: string) => void;
  set: (messageId: string, rating: Rating | undefined) => void;
};

const useFeedback = create<FeedbackStore>((set, get) => ({
  ratings: {},
  loaded: {},
  load: (threadId) => {
    if (get().loaded[threadId]) return;
    set((state) => ({ loaded: { ...state.loaded, [threadId]: true } }));
    void authFetch(`/api/feedback/thread/${encodeURIComponent(threadId)}`)
      .then((response) => (response.ok ? response.json() : { ratings: {} }))
      .then((data: { ratings: Record<string, Rating> }) =>
        set((state) => ({ ratings: { ...data.ratings, ...state.ratings } })),
      )
      .catch(() => set((state) => ({ loaded: { ...state.loaded, [threadId]: false } })));
  },
  set: (messageId, rating) => set((state) => ({ ratings: { ...state.ratings, [messageId]: rating } })),
}));

async function sendRating(threadId: string, messageId: string, rating: Rating | undefined) {
  const response = rating
    ? await authFetch("/api/feedback", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ threadId, messageId, ...rating }),
      })
    : await authFetch(`/api/feedback/${encodeURIComponent(threadId)}/${encodeURIComponent(messageId)}`, {
        method: "DELETE",
      });
  if (!response.ok) throw new Error(await errorMessage(response, "Feedback could not be saved."));
}

function FeedbackBar({ threadId, messageId }: { threadId: string; messageId: string }) {
  const current = useFeedback((state) => state.ratings[messageId]);
  const setLocal = useFeedback((state) => state.set);
  const load = useFeedback((state) => state.load);
  const [details, setDetails] = useState(false);
  const [reasons, setReasons] = useState<string[]>([]);
  const [comment, setComment] = useState("");
  const [status, setStatus] = useState<"idle" | "saving" | "thanks" | "error">("idle");
  const [error, setError] = useState("");

  useEffect(() => load(threadId), [load, threadId]);

  const save = async (next: Rating | undefined) => {
    const previous = current;
    setLocal(messageId, next);
    setStatus("saving");
    try {
      await sendRating(threadId, messageId, next);
      setStatus(next ? "thanks" : "idle");
    } catch (failure) {
      setLocal(messageId, previous);
      setError(failure instanceof Error ? failure.message : "Feedback could not be saved.");
      setStatus("error");
    }
  };

  const rate = (rating: "up" | "down") => {
    if (current?.rating === rating) {
      setDetails(false);
      void save(undefined);
      return;
    }
    setDetails(rating === "down");
    setReasons([]);
    setComment("");
    void save({ rating, reasons: [], comment: "" });
  };

  const submitDetails = () => {
    setDetails(false);
    void save({ rating: "down", reasons, comment: comment.trim() });
  };

  const toggleReason = (id: string) =>
    setReasons((list) => (list.includes(id) ? list.filter((item) => item !== id) : [...list, id]));

  return (
    <div className="qc-feedback">
      <div className="qc-feedback__row">
        <button
          type="button"
          className="qc-feedback__button"
          aria-pressed={current?.rating === "up"}
          aria-label="Good answer"
          title="Good answer"
          disabled={status === "saving"}
          onClick={() => rate("up")}
        >
          <ThumbsUp size={15} />
        </button>
        <button
          type="button"
          className="qc-feedback__button"
          aria-pressed={current?.rating === "down"}
          aria-label="Bad answer"
          title="Bad answer"
          disabled={status === "saving"}
          onClick={() => rate("down")}
        >
          <ThumbsDown size={15} />
        </button>
        <span className="qc-feedback__status" role="status">
          {status === "thanks" && !details ? "Thanks for the feedback." : null}
          {status === "error" ? error : null}
        </span>
      </div>

      {details ? (
        <form
          className="qc-feedback__details"
          onSubmit={(event) => {
            event.preventDefault();
            submitDetails();
          }}
        >
          <p className="qc-feedback__prompt">What went wrong?</p>
          <div className="qc-feedback__reasons">
            {REASONS.map((reason) => (
              <button
                key={reason.id}
                type="button"
                className="qc-feedback__chip"
                aria-pressed={reasons.includes(reason.id)}
                onClick={() => toggleReason(reason.id)}
              >
                {reason.label}
              </button>
            ))}
          </div>
          <textarea
            className="qc-feedback__comment"
            aria-label="Tell us more (optional)"
            placeholder="Tell us more (optional)"
            maxLength={1000}
            rows={2}
            value={comment}
            onChange={(event) => setComment(event.target.value)}
          />
          <div className="qc-feedback__actions">
            <button type="button" className="qc-feedback__skip" onClick={() => setDetails(false)}>
              Skip
            </button>
            <button type="submit" className="qc-feedback__send" disabled={!reasons.length && !comment.trim()}>
              Send
            </button>
          </div>
        </form>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------
// The message
// ------------------------------------------------------------------

export function QueryableAssistantMessage({ message, isStreaming }: { message: AssistantMessage; isStreaming: boolean }) {
  const processMessage = useThread((state) => state.processMessage);
  const updateMessage = useThread((state) => state.updateMessage);
  const threadId = useThreadList((state) => state.selectedThreadId);

  const { content, context, header } = useMemo(
    () => (message.content ? splitMessage(message.content) : { content: "", context: null }),
    [message.content],
  );
  const initialState = useMemo(() => parseState(context), [context]);

  const handleStateUpdate = useCallback(
    (state: Record<string, unknown>) => {
      const body = `${header ?? CONTENT_MARKER}\n${content}`;
      const withState = Object.keys(state).length ? `${body}\n${CONTEXT_MARKER}\n${JSON.stringify([state])}` : body;
      updateMessage({ ...message, content: withState });
    },
    [updateMessage, message, content, header],
  );

  const handleAction = useCallback(
    (event: ActionEvent) => {
      if (event.type === BuiltinActionType.ContinueConversation) {
        const contentPart = event.humanFriendlyMessage ? `${CONTENT_MARKER}\n${event.humanFriendlyMessage}` : "";
        const messageContext: unknown[] = [`User clicked: ${event.humanFriendlyMessage}`];
        if (event.formState) messageContext.push(event.formState);
        void processMessage({
          role: "user",
          content: `${contentPart}\n${CONTEXT_MARKER}\n${JSON.stringify(messageContext)}`,
        });
      } else if (event.type === BuiltinActionType.OpenUrl) {
        const url = event.params?.["url"];
        if (typeof url === "string" && url) window.open(url, "_blank", "noopener,noreferrer");
      }
    },
    [processMessage],
  );

  const shape = useMemo(() => describeResponse(content), [content]);

  const renderer = content ? (
    <Renderer
      response={content}
      library={openuiChatLibrary}
      isStreaming={isStreaming}
      onAction={handleAction}
      onStateUpdate={handleStateUpdate}
      initialState={initialState}
    />
  ) : null;

  return (
    <div className="openui-shell-thread-message-assistant openui-shell-thread-message-assistant--without-logo">
      <div className="openui-shell-thread-message-assistant__content">
        {shape.rich && message.id ? (
          <ArtifactResponse messageId={message.id} shape={shape} isStreaming={isStreaming}>
            {renderer}
          </ArtifactResponse>
        ) : (
          renderer
        )}
        {!isStreaming && content && threadId && message.id ? (
          <FeedbackBar threadId={threadId} messageId={message.id} />
        ) : null}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------
// Artifact-style responses
// ------------------------------------------------------------------

/**
 * Like a Claude artifact: an answer with charts, tables or other rich
 * components shows a short summary and a card in the chat, and the full
 * response (every component, not just one chart) opens in the side panel.
 * Plain-text answers stay inline.
 */

// Components that read as plain chat text. Anything else makes the answer an artifact.
const PLAIN = new Set([
  "Card", "CardHeader", "TextContent", "MarkDownRenderer", "Callout", "TextCallout", "Separator", "InlineHeader",
  "FollowUpBlock", "FollowUpItem", "Text", "BoldText", "Label", "Tag", "TagBlock", "Icon", "IconText", "Buttons", "Button",
]);

const KIND_LABELS: [RegExp, string][] = [
  [/Chart$/, "Chart"],
  [/Table$/, "Table"],
  [/^(MetricIndicator|OverviewCard)/, "Metrics"],
  [/^(ListBlock|EntityList|SectionBlock|Steps|Accordion)/, "List"],
  [/^(Tabs|Carousel)/, "Tabs"],
  [/^(Form|Input|Select|RadioGroup|CheckBoxGroup|Slider|DatePicker)/, "Form"],
  [/^CodeBlock/, "Code"],
  [/^Image/, "Images"],
];

type ResponseShape = { rich: boolean; title: string; summary: string; kinds: string[] };

function decode(literal: string) {
  try {
    return JSON.parse(`"${literal}"`) as string;
  } catch {
    return literal;
  }
}

function firstString(content: string, components: string) {
  const match = new RegExp(String.raw`\b(?:${components})\(\s*"((?:[^"\\]|\\.)*)"`).exec(content);
  return match ? decode(match[1]) : "";
}

function plainText(markdown: string) {
  return markdown
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/[#>*_`|]+/g, " ")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

export function describeResponse(content: string): ResponseShape {
  const used = new Set(Array.from(content.matchAll(/([A-Z][A-Za-z]+)\s*\(/g), (m) => m[1]));
  const richParts = [...used].filter((name) => !PLAIN.has(name));
  // Data parts of a chart or table (Series, Col, Slice…) do not get their own label.
  const kinds = [
    ...new Set(richParts.map((name) => KIND_LABELS.find(([re]) => re.test(name))?.[1]).filter((k): k is string => !!k)),
  ];
  const title = plainText(firstString(content, "CardHeader|InlineHeader")) || "Answer";
  let summary = plainText(firstString(content, "TextContent|MarkDownRenderer"));
  if (summary.length > 280) summary = `${summary.slice(0, 277).replace(/\s+\S*$/, "")}…`;
  return { rich: richParts.length > 0, title, summary, kinds };
}

function ArtifactResponse({
  messageId,
  shape,
  isStreaming,
  children,
}: {
  messageId: string;
  shape: ResponseShape;
  isStreaming: boolean;
  children: React.ReactNode;
}) {
  const viewId = `qc-answer:${messageId}`;
  const { isActive, open, toggle } = useDetailedView(viewId);

  // Open the panel automatically for an answer that is streaming in now
  // (not for answers loaded from history), once.
  const autoOpened = useRef(false);
  useEffect(() => {
    if (isStreaming && !autoOpened.current) {
      autoOpened.current = true;
      open();
    }
  }, [isStreaming, open]);

  return (
    <>
      {shape.summary ? <p className="qc-answer-lead">{shape.summary}</p> : null}
      <button
        type="button"
        className="qc-artifact-card"
        data-active={isActive}
        aria-expanded={isActive}
        aria-controls={viewId}
        onClick={toggle}
      >
        <span className="qc-artifact-card__icon" aria-hidden="true">
          {isStreaming ? <span className="qc-artifact-card__pulse" /> : <BarChart3 size={18} />}
        </span>
        <span className="qc-artifact-card__text">
          <strong>{shape.title}</strong>
          <span>
            {isStreaming ? "Building the response…" : shape.kinds.length ? shape.kinds.join(" · ") : "Full response"}
          </span>
        </span>
        <span className="qc-artifact-card__action">
          {isActive ? (
            <>
              <PanelRightClose size={14} /> Close
            </>
          ) : (
            <>
              <LayoutPanelLeft size={14} /> Open <ChevronRight size={13} />
            </>
          )}
        </span>
      </button>
      <DetailedViewPanel viewId={viewId} title={shape.title} className="qc-artifact-panel">
        <div className="qc-artifact-panel__body" id={viewId}>
          {children}
        </div>
      </DetailedViewPanel>
    </>
  );
}
