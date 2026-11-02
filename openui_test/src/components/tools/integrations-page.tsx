"use client";

import { useState } from "react";
import { Copy, Plug, Sparkles } from "lucide-react";

import { LoadState, ToolPage, useApi } from "@/components/tools/shared";

/** Integrations (GET /api/admin/integrations): what is connected now, and what to try next. */

type Live = { id: string; name: string; category: string; status: string; detail: string };
type Candidate = { id: string; name: string; effort: string; impact: string; why: string; recommended?: boolean };

const STATUS: Record<string, string> = { live: "Live", available: "Available", needs_key: "Needs key" };
const EFFORT: Record<string, string> = { S: "Small (days)", M: "Medium (1–2 weeks)", L: "Large (weeks)" };

export function IntegrationsPage() {
  const { data, error, loading, reload } = useApi<{ live: Live[]; candidates: Candidate[] }>("/api/admin/integrations");
  const [copied, setCopied] = useState(false);
  // Rendered only after the client fetch, so window is always available here.
  const origin = typeof window === "undefined" ? "https://<your-app>" : window.location.origin;

  const curl = [
    `curl ${origin}/api/ask \\`,
    `  -H "Authorization: Bearer qc-..." \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '{"question": "How many companies are in India?"}'`,
  ].join("\n");

  return (
    <ToolPage
      icon={<Plug size={13} />}
      eyebrow="Integrations · Admin"
      title="How the agent plugs into our tools"
      description="What is connected today, and the shortlist for the first new integration."
    >
      <LoadState loading={loading} error={error} onRetry={reload} />
      {data && (
        <>
          <section>
            <h2 className="qc-section-title"><Plug size={15} /> Connected now</h2>
            <div className="qc-integrations">
              {data.live.map((item) => (
                <article key={item.id} className="qc-tile qc-integration" data-status={item.status}>
                  <header className="qc-tile__head">
                    <h3 className="qc-tile__title">{item.name}</h3>
                    <span className="qc-integration__status">{STATUS[item.status] ?? item.status}</span>
                  </header>
                  <span className="qc-muted">{item.category}</span>
                  <p>{item.detail}</p>
                </article>
              ))}
            </div>
          </section>

          <section>
            <h2 className="qc-section-title"><Sparkles size={15} /> Candidates for the next integration</h2>
            <div className="qc-integrations">
              {data.candidates.map((item) => (
                <article key={item.id} className="qc-tile qc-integration" data-recommended={item.recommended ?? false}>
                  <header className="qc-tile__head">
                    <h3 className="qc-tile__title">{item.name}</h3>
                    {item.recommended && <span className="qc-pill">Try first</span>}
                  </header>
                  <p>{item.why}</p>
                  <dl className="qc-integration__facts">
                    <div><dt>Effort</dt><dd>{EFFORT[item.effort] ?? item.effort}</dd></div>
                    <div><dt>Impact</dt><dd>{item.impact}</dd></div>
                  </dl>
                </article>
              ))}
            </div>
          </section>

          <section className="qc-tile">
            <h2 className="qc-tile__title">Use it from any tool today</h2>
            <p className="qc-muted">
              Create a personal key in Settings → API keys, then call the agent from scripts, Zapier, Power Automate or any
              tool that can make an HTTP request.
            </p>
            <pre className="qi-code qc-integration__code">{curl}</pre>
            <button
              type="button"
              className="qc-ghost-button"
              onClick={() => {
                void navigator.clipboard?.writeText(curl).then(() => {
                  setCopied(true);
                  window.setTimeout(() => setCopied(false), 1500);
                });
              }}
            >
              <Copy size={13} /> {copied ? "Copied" : "Copy"}
            </button>
          </section>
        </>
      )}
    </ToolPage>
  );
}
