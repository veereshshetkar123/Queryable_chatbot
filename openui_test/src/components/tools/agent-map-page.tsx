"use client";

import { useMemo, useState } from "react";
import { Bot, Database, Network } from "lucide-react";

import { LoadState, ToolPage, useApi } from "@/components/tools/shared";

/**
 * Agent map (GET /api/admin/agents): every agent in the system, how they
 * hand off to each other, and which datasets each one sits on. Click an
 * agent to highlight its data; click a dataset to see which agents use it.
 */

type Agent = {
  id: string;
  name: string;
  stage: string;
  role: string;
  model: string | null;
  status: "live" | "off" | "needs_key";
  reads: string[];
  writes?: string[];
};
type DataNode = { id: string; name: string; documents: number; fields: number; kind: "sample" | "hr" | "upload"; geo: boolean };
type Edge = { from: string; to: string; label: string };
type AgentMap = { agents: Agent[]; data: DataNode[]; edges: Edge[] };

const W = 150;
const H = 58;
// Node centres in a 1180 x 430 viewBox, in pipeline order left to right.
const POS: Record<string, [number, number]> = {
  guardrails: [85, 160],
  router: [255, 160],
  memory: [255, 310],
  query: [425, 160],
  validator: [595, 160],
  executor: [765, 160],
  ingest: [765, 310],
  geo: [935, 60],
  insights: [935, 260],
  answer: [1100, 160],
};

const KIND_LABEL: Record<DataNode["kind"], string> = { sample: "Built-in", hr: "HR dataset", upload: "Uploaded" };
const STATUS_LABEL: Record<Agent["status"], string> = { live: "Live", off: "Off", needs_key: "Needs API key" };

function edgePath(a: [number, number], b: [number, number], from: string, to: string) {
  const [ax, ay] = a;
  const [bx, by] = b;
  if (from === "router" && to === "answer") {
    // General chat skips the data path: route it underneath everything.
    const y = 395;
    return { d: `M ${ax} ${ay + H / 2} C ${ax} ${y}, ${bx} ${y}, ${bx} ${by + H / 2}`, lx: (ax + bx) / 2, ly: y - 6 };
  }
  if (bx < ax) {
    // Retry loop: arc above.
    const y = ay - 95;
    return { d: `M ${ax - 30} ${ay - H / 2} C ${ax - 30} ${y}, ${bx + 30} ${y}, ${bx + 30} ${by - H / 2}`, lx: (ax + bx) / 2, ly: y + 18 };
  }
  if (ax === bx) {
    const up = by < ay;
    return { d: `M ${ax} ${up ? ay - H / 2 : ay + H / 2} L ${bx} ${up ? by + H / 2 : by - H / 2}`, lx: ax + 6, ly: (ay + by) / 2 };
  }
  const sx = ax + W / 2;
  const ex = bx - W / 2;
  const mx = (sx + ex) / 2;
  return { d: `M ${sx} ${ay} C ${mx} ${ay}, ${mx} ${by}, ${ex} ${by}`, lx: mx, ly: (ay + by) / 2 - 6 };
}

export function AgentMapPage() {
  const { data, error, loading, reload } = useApi<AgentMap>("/api/admin/agents");
  const [agentId, setAgentId] = useState<string>("query");
  const [dataId, setDataId] = useState<string | null>(null);

  const agents = useMemo(() => data?.agents ?? [], [data]);
  const byId = useMemo(() => Object.fromEntries(agents.map((a) => [a.id, a])), [agents]);
  const selected = dataId ? null : byId[agentId];
  const touches = (agent: Agent, id: string) => agent.reads.includes(id) || (agent.writes ?? []).includes(id);

  const litAgents = new Set(
    dataId ? agents.filter((a) => touches(a, dataId)).map((a) => a.id) : selected ? [selected.id] : [],
  );
  const litData = new Set(dataId ? [dataId] : selected ? [...selected.reads, ...(selected.writes ?? [])] : []);
  const groups = (["upload", "sample", "hr"] as const)
    .map((kind) => ({ kind, items: (data?.data ?? []).filter((d) => d.kind === kind) }))
    .filter((g) => g.items.length);
  const users = dataId ? agents.filter((a) => touches(a, dataId)) : [];
  const dataset = dataId ? data?.data.find((d) => d.id === dataId) : null;

  return (
    <ToolPage
      icon={<Network size={13} />}
      eyebrow="Agent map · Admin"
      title="Every agent, in one place"
      description="Which agents exist, how a question flows between them, and the data each one sits on. Click an agent or a dataset."
    >
      <LoadState loading={loading} error={error} onRetry={reload} />
      {data && (
        <>
          <section className="qc-tile qc-agentmap" aria-label="Agent flow">
            <div className="qc-agentmap__scroll">
              <svg viewBox="0 0 1180 430" className="qc-agentmap__svg" role="img" aria-label="Agents and their hand-offs">
                <defs>
                  <marker id="qc-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                    <path d="M 0 0 L 10 5 L 0 10 z" className="qc-agentmap__arrow" />
                  </marker>
                </defs>
                {data.edges.map((edge) => {
                  const a = POS[edge.from];
                  const b = POS[edge.to];
                  if (!a || !b) return null;
                  const { d, lx, ly } = edgePath(a, b, edge.from, edge.to);
                  const lit = litAgents.has(edge.from) || litAgents.has(edge.to);
                  return (
                    <g key={`${edge.from}-${edge.to}`} className="qc-agentmap__edge" data-lit={lit}>
                      <path d={d} markerEnd="url(#qc-arrow)" />
                      <text x={lx} y={ly} textAnchor="middle">{edge.label}</text>
                    </g>
                  );
                })}
                {agents.map((agent) => {
                  const pos = POS[agent.id];
                  if (!pos) return null;
                  const [x, y] = pos;
                  return (
                    <g
                      key={agent.id}
                      className="qc-agentmap__node"
                      data-status={agent.status}
                      data-lit={litAgents.has(agent.id)}
                      data-dim={litAgents.size > 0 && !litAgents.has(agent.id)}
                      transform={`translate(${x - W / 2} ${y - H / 2})`}
                      role="button"
                      tabIndex={0}
                      aria-label={`${agent.name}: ${STATUS_LABEL[agent.status]}`}
                      onClick={() => {
                        setAgentId(agent.id);
                        setDataId(null);
                      }}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setAgentId(agent.id);
                          setDataId(null);
                        }
                      }}
                    >
                      <rect width={W} height={H} rx={14} />
                      <circle cx={16} cy={18} r={4.5} className="qc-agentmap__status" />
                      <text x={28} y={22} className="qc-agentmap__name">{agent.name}</text>
                      <text x={16} y={42} className="qc-agentmap__sub">
                        {agent.reads.length || agent.writes?.length
                          ? `${(agent.writes ?? agent.reads).length} dataset${(agent.writes ?? agent.reads).length === 1 ? "" : "s"}`
                          : agent.model
                            ? agent.model.split("/").pop()
                            : agent.stage}
                      </text>
                    </g>
                  );
                })}
              </svg>
            </div>
            <p className="qc-agentmap__legend">
              <span data-status="live" /> Live <span data-status="off" /> Off <span data-status="needs_key" /> Needs API key
            </p>
          </section>

          <div className="qc-agentmap__split">
            <section className="qc-tile" aria-live="polite">
              {selected && (
                <>
                  <h2 className="qc-tile__title"><Bot size={15} /> {selected.name}</h2>
                  <p className="qc-agentmap__role">{selected.role}</p>
                  <dl className="qc-agentmap__facts">
                    <div><dt>Stage</dt><dd>{selected.stage}</dd></div>
                    <div><dt>Status</dt><dd>{STATUS_LABEL[selected.status]}</dd></div>
                    <div><dt>Model</dt><dd>{selected.model ?? "Rules, no LLM"}</dd></div>
                    <div>
                      <dt>{selected.writes ? "Writes" : "Reads"}</dt>
                      <dd>
                        {(selected.writes ?? selected.reads).length
                          ? `${(selected.writes ?? selected.reads).length} dataset(s), highlighted`
                          : "No datasets"}
                      </dd>
                    </div>
                    <div>
                      <dt>Hands off to</dt>
                      <dd>{data.edges.filter((e) => e.from === selected.id).map((e) => byId[e.to]?.name).join(", ") || "The user"}</dd>
                    </div>
                  </dl>
                </>
              )}
              {dataset && (
                <>
                  <h2 className="qc-tile__title"><Database size={15} /> {dataset.name}</h2>
                  <p className="qc-agentmap__role">
                    {KIND_LABEL[dataset.kind]} · {dataset.documents.toLocaleString()} rows · {dataset.fields} fields
                    {dataset.geo ? " · has location fields" : ""}
                  </p>
                  <p className="qc-section-title">Used by</p>
                  <div className="qc-agentmap__chips">
                    {users.map((a) => (
                      <button key={a.id} type="button" className="qc-ghost-button" onClick={() => { setAgentId(a.id); setDataId(null); }}>
                        <Bot size={13} /> {a.name}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </section>

            <section className="qc-tile" aria-label="Datasets">
              <h2 className="qc-tile__title"><Database size={15} /> Data layer</h2>
              {groups.map((group) => (
                <div key={group.kind} className="qc-agentmap__group">
                  <p className="qc-section-title">{KIND_LABEL[group.kind]}</p>
                  <div className="qc-agentmap__chips">
                    {group.items.map((d) => (
                      <button
                        key={d.id}
                        type="button"
                        className="qc-agentmap__data"
                        data-kind={d.kind}
                        data-lit={litData.has(d.id)}
                        aria-pressed={dataId === d.id}
                        onClick={() => setDataId(d.id)}
                      >
                        <span>{d.name}</span>
                        <small>{d.documents.toLocaleString()}</small>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </section>
          </div>
        </>
      )}
    </ToolPage>
  );
}
