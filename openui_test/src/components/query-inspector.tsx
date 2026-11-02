"use client";

import { defineArtifactRenderer } from "@openuidev/react-ui";
import { Database, ShieldCheck, TriangleAlert } from "lucide-react";

/**
 * Branded renderers for the backend's tool calls, registered with OpenUI's
 * official artifact-renderer API. The backend emits `query_mongodb` and
 * `route_question` as AG-UI tool calls; these renderers show them as a
 * compact inline card plus a full "query inspector" side panel.
 */

type QueryArgs = {
  collection?: string;
  operation?: string;
  filters?: unknown;
  pipeline?: unknown[];
  fields?: string[];
  field?: string;
};

type QueryResult = {
  ok?: boolean;
  rows_returned?: number;
  truncated?: boolean;
  latency_ms?: number;
  preview?: Record<string, unknown>[];
  error?: string;
};

type QueryProps = { args: QueryArgs; result: QueryResult | null; streaming: boolean; id: string };

function parseJSON<T>(value: unknown): T | null {
  if (value == null) return null;
  if (typeof value === "object") return value as T;
  try {
    return JSON.parse(String(value)) as T;
  } catch {
    return null;
  }
}

function cell(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function PreviewTable({ rows }: { rows: Record<string, unknown>[] }) {
  const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row)))).slice(0, 8);
  if (!rows.length) return <p className="qi-muted">No rows returned.</p>;
  return (
    <div className="qi-table-wrap">
      <table className="qi-table">
        <thead>
          <tr>{columns.map((column) => <th key={column} scope="col">{column}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>{columns.map((column) => <td key={column}>{cell(row[column])}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export const queryInspectorRenderer = defineArtifactRenderer<QueryProps>({
  type: "qc_mongodb_query",
  toolName: "query_mongodb",
  parser: ({ args, response }, { isStreaming }) => {
    const stored = parseJSON<QueryResult & { query?: QueryArgs }>(response);
    // A saved artifact (Artifacts library) has no tool-call args: the backend
    // keeps the executed query in its content instead (backend/artifacts.py).
    const parsedArgs = parseJSON<QueryArgs>(args) ?? stored?.query ?? {};
    const { query: _query, ...result } = stored ?? {};
    void _query;
    const id = `${parsedArgs.collection ?? "query"}-${JSON.stringify(parsedArgs).length}`;
    return {
      props: { args: parsedArgs, result: stored ? result : null, streaming: isStreaming, id },
      meta: null,
    };
  },
  preview: ({ args, result, streaming }, controls) => {
    const failed = result && result.ok === false;
    return (
      <button type="button" className={`qi-chip ${failed ? "qi-chip--error" : ""}`} onClick={controls.toggle}>
        {failed ? <TriangleAlert size={15} /> : <Database size={15} />}
        <span className="qi-chip__title">
          {streaming || !result
            ? "Running validated query…"
            : failed
              ? "Query did not pass validation"
              : `${args.operation ?? "query"} · ${args.collection ?? ""}`}
        </span>
        {result?.ok && (
          <span className="qi-chip__meta">
            {result.rows_returned} row{result.rows_returned === 1 ? "" : "s"}
            {typeof result.latency_ms === "number" ? ` · ${(result.latency_ms / 1000).toFixed(1)}s` : ""}
          </span>
        )}
        <span className="qi-chip__badge">
          <ShieldCheck size={13} /> read-only
        </span>
      </button>
    );
  },
  actual: ({ args, result }) => (
    <div className="qi-panel">
      <h2 className="qi-panel__title">
        <Database size={18} /> Query inspector
      </h2>
      <dl className="qi-facts">
        <div><dt>Collection</dt><dd>{args.collection ?? "—"}</dd></div>
        <div><dt>Operation</dt><dd>{args.operation ?? "—"}</dd></div>
        <div><dt>Rows</dt><dd>{result?.rows_returned ?? "—"}{result?.truncated ? " (limit reached)" : ""}</dd></div>
        <div><dt>Validation</dt><dd>{result?.ok === false ? "Rejected" : "Passed allowlist validator"}</dd></div>
      </dl>
      <h3 className="qi-panel__subtitle">Executed query</h3>
      <pre className="qi-code">{JSON.stringify(args, null, 2)}</pre>
      {result?.preview && (
        <>
          <h3 className="qi-panel__subtitle">Result preview</h3>
          <PreviewTable rows={result.preview} />
        </>
      )}
      {result?.error && <p className="qi-error">{result.error}</p>}
    </div>
  ),
  label: "MongoDB query",
  icon: <Database size={16} />,
});

type RouteResult = { route?: string; confidence?: number; source?: string };

const ROUTE_LABELS: Record<string, string> = {
  database_query: "Database question",
  general_chat: "General question",
  browser_task: "Browser task",
};

export const routeRenderer = defineArtifactRenderer<{ result: RouteResult | null }>({
  type: "qc_route",
  toolName: "route_question",
  parser: ({ response }) => ({ props: { result: parseJSON<RouteResult>(response) }, meta: null }),
  preview: ({ result }) => (
    <div className="qi-route" aria-label="Routing decision">
      <span className="qi-route__dot" />
      {result ? (
        <>
          Routed as <strong>{ROUTE_LABELS[result.route ?? ""] ?? result.route}</strong>
          <span className="qi-muted">
            {" "}by {result.source === "jev" ? "Jev" : result.source}
            {typeof result.confidence === "number" ? ` · ${(result.confidence * 100).toFixed(0)}%` : ""}
          </span>
        </>
      ) : (
        "Routing…"
      )}
    </div>
  ),
  actual: ({ result }) => <pre className="qi-code">{JSON.stringify(result, null, 2)}</pre>,
  label: "Routing",
});

export const artifactRenderers = [queryInspectorRenderer, routeRenderer];
