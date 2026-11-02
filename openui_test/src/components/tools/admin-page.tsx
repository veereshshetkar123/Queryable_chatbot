"use client";

import { Fragment, useMemo, useState, type FormEvent } from "react";
import {
  Activity,
  Ban,
  Boxes,
  CheckCircle2,
  CircleDot,
  Coins,
  KeyRound,
  LayoutDashboard,
  LogOut,
  MessageSquare,
  RefreshCw,
  Search,
  ServerCog,
  ShieldCheck,
  ThumbsDown,
  ThumbsUp,
  UserPlus,
  Users,
  XCircle,
} from "lucide-react";

import { BarList, Donut, TrendChart } from "@/components/charts";
import { LoadState, ToolPage, useApi } from "@/components/tools/shared";
import { authFetch, errorMessage } from "@/lib/api";
import { formatValue } from "@/lib/geo";

/* ------------------------------------------------------------------ types */

type Overview = {
  kpis: {
    users: number;
    disabled_users: number;
    admins: number;
    active_today: number;
    active_7d: number;
    questions_today: number;
    questions_14d: number;
    tokens_14d: number;
    cost_14d_usd: number;
    conversations: number;
    artifacts: number;
    satisfaction: number | null;
    ratings: number;
    active_sessions: number;
  };
  days: { day: string; messages: number; tokens: number; cost_usd: number; active_users: number }[];
  plans: { id: string; name: string; users: number }[];
  roles: Record<string, number>;
  top_users: { username: string; display_name: string; messages: number }[];
  artifact_types: Record<string, number>;
  system: {
    mongodb: boolean;
    openrouter_configured: boolean;
    default_model: string;
    jev_enabled: boolean;
    graphiti_enabled: boolean;
    langfuse_enabled: boolean;
    signup_enabled: boolean;
    plan_limits_enforced: boolean;
    cookie_secure: boolean;
  };
  live: {
    requests: number;
    errors: number;
    fallbacks: number;
    latency_p50_s: number | null;
    latency_p95_s: number | null;
    total_tokens: number;
    total_cost_usd: number;
    by_route: Record<string, number>;
  };
};

type AdminUser = {
  username: string;
  display_name: string;
  role: string;
  plan: string;
  disabled: boolean;
  created_at: string | null;
  last_active: string | null;
  signed_in: boolean;
  messages_14d: number;
  conversations: number;
  artifacts: number;
  api_keys: number;
};

type UserList = { users: AdminUser[]; plans: { id: string; name: string }[]; roles: string[]; me: string };

type Feedback = {
  up: number;
  down: number;
  satisfaction: number | null;
  by_route: { route: string; up: number; down: number }[];
  reasons: Record<string, number>;
  recent_down: {
    at: string;
    username: string;
    question: string;
    reasons: string[];
    comment: string;
    route: string | null;
    query: unknown;
    trace_id: string | null;
  }[];
};

type Audit = { events: { at: string; actor: string; action: string; target: string; details: Record<string, unknown> }[] };

const TABS = [
  { id: "overview", label: "Overview", icon: <LayoutDashboard size={15} /> },
  { id: "users", label: "Users", icon: <Users size={15} /> },
  { id: "feedback", label: "Feedback", icon: <ThumbsUp size={15} /> },
  { id: "activity", label: "Activity log", icon: <Activity size={15} /> },
  { id: "system", label: "System", icon: <ServerCog size={15} /> },
] as const;

type TabId = (typeof TABS)[number]["id"];

const ROUTES: Record<string, string> = {
  database_query: "Database questions",
  general_chat: "General questions",
  browser_task: "Browser tasks",
  blocked: "Blocked by guardrails",
  unknown: "Unknown",
};

const ARTIFACT_TYPES: Record<string, string> = {
  qc_visual_analysis: "Charts",
  qc_data_insights: "Insight cards",
  qc_geo_map: "Maps",
  qc_mongodb_query: "Queries",
};

/* ---------------------------------------------------------------- helpers */

async function send(url: string, method: string, body?: unknown) {
  const response = await authFetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await errorMessage(response, "Something went wrong. Please try again."));
  return response.json();
}

function relative(iso: string | null) {
  if (!iso) return "Never";
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diff / 60000);
  if (minutes < 2) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} d ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

const percent = (value: number | null) => (value == null ? "—" : `${Math.round(value * 100)}%`);
const seconds = (value: number | null) => (value == null ? "—" : `${value.toFixed(1)}s`);
const shortDay = (day: string) =>
  new Date(`${day}T00:00:00Z`).toLocaleDateString(undefined, { day: "numeric", month: "short", timeZone: "UTC" });

function Kpi({ label, value, hint, icon, tone }: { label: string; value: string; hint: string; icon: React.ReactNode; tone?: string }) {
  return (
    <article className={`qc-kpi qc-admin-kpi ${tone ? `qc-admin-kpi--${tone}` : ""}`}>
      <span className="qc-admin-kpi__icon" aria-hidden="true">{icon}</span>
      <span className="qc-kpi__label">{label}</span>
      <span className="qc-kpi__value">{value}</span>
      <span className="qc-kpi__hint">{hint}</span>
    </article>
  );
}

function Notice({ error, ok }: { error: string; ok: string }) {
  if (error) return <p className="qc-set-status qc-set-status--error" role="alert">{error}</p>;
  if (ok) return <p className="qc-set-status" role="status"><CheckCircle2 size={13} /> {ok}</p>;
  return null;
}

/* --------------------------------------------------------------- overview */

function OverviewTab({ data }: { data: Overview }) {
  const k = data.kpis;
  const tiles = [
    { label: "Users", value: formatValue(k.users), hint: `${k.admins} admin${k.admins === 1 ? "" : "s"} · ${k.disabled_users} disabled`, icon: <Users size={16} /> },
    { label: "Active today", value: formatValue(k.active_today), hint: `${k.active_7d} in the last 7 days`, icon: <CircleDot size={16} />, tone: "success" },
    { label: "Questions today", value: formatValue(k.questions_today), hint: `${formatValue(k.questions_14d)} in 14 days`, icon: <MessageSquare size={16} /> },
    { label: "Satisfaction", value: percent(k.satisfaction), hint: `${k.ratings} rating${k.ratings === 1 ? "" : "s"}`, icon: <ThumbsUp size={16} />, tone: "warm" },
    { label: "Model cost", value: `$${k.cost_14d_usd.toFixed(2)}`, hint: `${formatValue(k.tokens_14d)} tokens · 14 days`, icon: <Coins size={16} /> },
    { label: "Artifacts saved", value: formatValue(k.artifacts), hint: `${formatValue(k.conversations)} conversations`, icon: <Boxes size={16} /> },
  ];
  const questions = data.days.map((d) => ({ label: shortDay(d.day), value: d.messages }));
  const active = data.days.map((d) => ({ label: shortDay(d.day), value: d.active_users }));
  const artifacts = Object.entries(data.artifact_types).map(([type, value]) => ({ label: ARTIFACT_TYPES[type] ?? type, value }));
  const plans = data.plans.filter((p) => p.users > 0).map((p) => ({ label: p.name, value: p.users }));

  return (
    <>
      <section className="qc-kpi-row qc-admin-kpis" aria-label="Workspace metrics">
        {tiles.map((tile) => <Kpi key={tile.label} {...tile} />)}
      </section>

      <section className="qc-panel-grid qc-admin-grid">
        <article className="qc-tile qc-tile--wide">
          <header className="qc-tile__head">
            <h2 className="qc-tile__title"><MessageSquare size={15} /> Questions per day</h2>
            <span className="qc-muted">last 14 days, all users</span>
          </header>
          <TrendChart rows={questions} />
        </article>
        <article className="qc-tile">
          <header className="qc-tile__head">
            <h2 className="qc-tile__title"><CircleDot size={15} /> Active users per day</h2>
          </header>
          <TrendChart rows={active} height={180} />
        </article>
        <article className="qc-tile">
          <header className="qc-tile__head">
            <h2 className="qc-tile__title"><Users size={15} /> Plan mix</h2>
          </header>
          {plans.length ? <Donut rows={plans} centerLabel="users" /> : <p className="qc-muted">No users yet.</p>}
        </article>
        <article className="qc-tile">
          <header className="qc-tile__head">
            <h2 className="qc-tile__title"><Activity size={15} /> Most active users</h2>
            <span className="qc-muted">questions · 14 days</span>
          </header>
          {data.top_users.length ? (
            <BarList rows={data.top_users.map((u) => ({ label: u.display_name, value: u.messages }))} max={6} />
          ) : (
            <p className="qc-muted">Nobody has asked anything in the last 14 days.</p>
          )}
        </article>
        <article className="qc-tile">
          <header className="qc-tile__head">
            <h2 className="qc-tile__title"><Boxes size={15} /> Artifacts by type</h2>
          </header>
          {artifacts.length ? <BarList rows={artifacts} /> : <p className="qc-muted">Artifacts appear here once people ask data questions.</p>}
        </article>
      </section>
    </>
  );
}

/* ------------------------------------------------------------------ users */

function AddUserForm({ plans, onCreated }: { plans: { id: string; name: string }[]; onCreated: (username: string) => void }) {
  const [form, setForm] = useState({ username: "", display_name: "", password: "", role: "analyst", plan: plans[0]?.id ?? "free" });
  const [state, setState] = useState({ error: "", ok: "" });
  const [busy, setBusy] = useState(false);
  const set = (key: keyof typeof form) => (event: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: event.target.value }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      const body = await send("/api/admin/users", "POST", form);
      setState({ error: "", ok: `Created @${body.username}. Share the password with them securely.` });
      setForm((f) => ({ ...f, username: "", display_name: "", password: "" }));
      onCreated(body.username);
    } catch (err) {
      setState({ error: (err as Error).message, ok: "" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="qc-set-card qc-admin-add" onSubmit={submit}>
      <h3 className="qc-set-card__title"><UserPlus size={15} /> Add a user</h3>
      <div className="qc-admin-add__grid">
        <label>
          <span>Username</span>
          <input className="qc-input" value={form.username} onChange={set("username")} placeholder="e.g. priya" required minLength={3} maxLength={32} autoComplete="off" />
        </label>
        <label>
          <span>Display name</span>
          <input className="qc-input" value={form.display_name} onChange={set("display_name")} placeholder="Priya Shah" maxLength={80} />
        </label>
        <label>
          <span>Temporary password</span>
          <input className="qc-input" type="password" value={form.password} onChange={set("password")} required minLength={8} autoComplete="new-password" />
        </label>
        <label>
          <span>Role</span>
          <select className="qc-select" value={form.role} onChange={set("role")}>
            <option value="analyst">Analyst</option>
            <option value="admin">Administrator</option>
          </select>
        </label>
        <label>
          <span>Plan</span>
          <select className="qc-select" value={form.plan} onChange={set("plan")}>
            {plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.name}</option>)}
          </select>
        </label>
        <div className="qc-admin-add__submit">
          <button className="qc-primary-button" type="submit" disabled={busy || form.username.length < 3 || form.password.length < 8}>
            <UserPlus size={14} /> Create user
          </button>
        </div>
      </div>
      <Notice {...state} />
    </form>
  );
}

function PasswordForm({ user, onDone }: { user: AdminUser; onDone: (message: string, error?: boolean) => void }) {
  const [password, setPassword] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const body = await send(`/api/admin/users/${encodeURIComponent(user.username)}/password`, "POST", { new_password: password });
      onDone(`New password set for @${user.username}; ${body.sessions_revoked} session${body.sessions_revoked === 1 ? "" : "s"} signed out.`);
    } catch (err) {
      onDone((err as Error).message, true);
    }
  };
  return (
    <form className="qc-admin-reset" onSubmit={submit}>
      <KeyRound size={14} />
      <span>New password for <b>@{user.username}</b></span>
      <input
        className="qc-input"
        type="password"
        autoComplete="new-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        minLength={8}
        autoFocus
        aria-label={`New password for ${user.username}`}
      />
      <button className="qc-primary-button" type="submit" disabled={password.length < 8}>Set password</button>
      <button className="qc-ghost-button" type="button" onClick={() => onDone("")}>Cancel</button>
    </form>
  );
}

function UsersTab() {
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<"all" | "active" | "disabled" | "admins">("all");
  const [adding, setAdding] = useState(false);
  const [resetFor, setResetFor] = useState<string | null>(null);
  const [state, setState] = useState({ error: "", ok: "" });
  const url = q.trim() ? `/api/admin/users?q=${encodeURIComponent(q.trim())}` : "/api/admin/users";
  const { data, error, loading, reload } = useApi<UserList>(url);

  const users = useMemo(() => {
    const all = data?.users ?? [];
    if (filter === "active") return all.filter((u) => !u.disabled);
    if (filter === "disabled") return all.filter((u) => u.disabled);
    if (filter === "admins") return all.filter((u) => u.role === "admin");
    return all;
  }, [data, filter]);

  const patch = async (user: AdminUser, change: Partial<AdminUser>, message: string) => {
    try {
      await send(`/api/admin/users/${encodeURIComponent(user.username)}`, "PATCH", change);
      setState({ error: "", ok: message });
      reload();
    } catch (err) {
      setState({ error: (err as Error).message, ok: "" });
    }
  };

  const toggleDisabled = (user: AdminUser) => {
    if (!user.disabled && !window.confirm(`Disable @${user.username}? They are signed out at once and can't sign in until re-enabled.`)) return;
    void patch(user, { disabled: !user.disabled }, user.disabled ? `@${user.username} can sign in again.` : `@${user.username} is disabled and signed out.`);
  };

  const signOut = async (user: AdminUser) => {
    if (!window.confirm(`Sign @${user.username} out of every device?`)) return;
    try {
      const body = await send(`/api/admin/users/${encodeURIComponent(user.username)}/sessions/revoke`, "POST");
      setState({ error: "", ok: `Signed @${user.username} out of ${body.sessions_revoked} session${body.sessions_revoked === 1 ? "" : "s"}.` });
      reload();
    } catch (err) {
      setState({ error: (err as Error).message, ok: "" });
    }
  };

  const counts = {
    all: data?.users.length ?? 0,
    active: data?.users.filter((u) => !u.disabled).length ?? 0,
    disabled: data?.users.filter((u) => u.disabled).length ?? 0,
    admins: data?.users.filter((u) => u.role === "admin").length ?? 0,
  };

  return (
    <>
      <div className="qc-admin-toolbar">
        <label className="qc-admin-search">
          <Search size={14} aria-hidden="true" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name or username" aria-label="Search users" />
        </label>
        <div className="qc-segmented" role="tablist" aria-label="Filter users">
          {(["all", "active", "disabled", "admins"] as const).map((id) => (
            <button key={id} type="button" role="tab" aria-selected={filter === id} className={filter === id ? "is-active" : ""} onClick={() => setFilter(id)}>
              {id.charAt(0).toUpperCase() + id.slice(1)} <span className="qc-admin-count">{counts[id]}</span>
            </button>
          ))}
        </div>
        <button type="button" className="qc-primary-button" onClick={() => setAdding((v) => !v)} aria-expanded={adding}>
          <UserPlus size={14} /> Add user
        </button>
      </div>

      {adding && data && <AddUserForm plans={data.plans} onCreated={() => reload()} />}
      <Notice {...state} />

      <section className="qc-set-card qc-set-card--flush">
        <LoadState loading={loading && !data} error={error} onRetry={reload} />
        {data && users.length === 0 && <p className="qc-muted qc-set-empty">No users match.</p>}
        {data && users.length > 0 && (
          <div className="qc-table-wrap">
            <table className="qc-keys qc-admin-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Role</th>
                  <th>Plan</th>
                  <th>Status</th>
                  <th className="is-num">Questions <small>14d</small></th>
                  <th className="is-num">Chats</th>
                  <th className="is-num">Artifacts</th>
                  <th>Last active</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {users.map((user) => {
                  const isMe = user.username === data.me;
                  return (
                    <Fragment key={user.username}>
                      <tr className={user.disabled ? "is-disabled" : ""}>
                        <td>
                          <span className="qc-admin-user">
                            <span className={`qc-admin-user__avatar ${user.role === "admin" ? "is-admin" : ""}`} aria-hidden="true">
                              {user.display_name.slice(0, 1).toUpperCase()}
                              {user.signed_in && !user.disabled && <i className="qc-admin-user__online" title="Signed in" />}
                            </span>
                            <span className="qc-admin-user__text">
                              <strong>{user.display_name} {isMe && <span className="qc-pill qc-admin-you">You</span>}</strong>
                              <span>@{user.username} · joined {relative(user.created_at)}</span>
                            </span>
                          </span>
                        </td>
                        <td>
                          <select
                            className="qc-select qc-select--compact"
                            value={user.role}
                            disabled={isMe}
                            title={isMe ? "You can't change your own role" : undefined}
                            onChange={(e) => void patch(user, { role: e.target.value }, `@${user.username} is now ${e.target.value === "admin" ? "an administrator" : "an analyst"}.`)}
                            aria-label={`Role of ${user.username}`}
                          >
                            <option value="analyst">Analyst</option>
                            <option value="admin">Admin</option>
                          </select>
                        </td>
                        <td>
                          <select
                            className="qc-select qc-select--compact"
                            value={user.plan}
                            onChange={(e) => void patch(user, { plan: e.target.value }, `@${user.username} moved to the ${e.target.value} plan.`)}
                            aria-label={`Plan of ${user.username}`}
                          >
                            {data.plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.name}</option>)}
                          </select>
                        </td>
                        <td>
                          <span className={`qc-admin-status ${user.disabled ? "is-off" : "is-on"}`}>
                            {user.disabled ? <XCircle size={12} /> : <CheckCircle2 size={12} />}
                            {user.disabled ? "Disabled" : "Active"}
                          </span>
                        </td>
                        <td className="is-num">{formatValue(user.messages_14d)}</td>
                        <td className="is-num">{formatValue(user.conversations)}</td>
                        <td className="is-num">{formatValue(user.artifacts)}</td>
                        <td>{relative(user.last_active)}</td>
                        <td>
                          <span className="qc-admin-actions">
                            <button type="button" className="qc-icon-button" title="Set a new password" aria-label={`Set a new password for ${user.username}`} onClick={() => setResetFor(resetFor === user.username ? null : user.username)}>
                              <KeyRound size={15} />
                            </button>
                            <button type="button" className="qc-icon-button" title="Sign out everywhere" aria-label={`Sign ${user.username} out everywhere`} disabled={isMe || !user.signed_in} onClick={() => void signOut(user)}>
                              <LogOut size={15} />
                            </button>
                            <button
                              type="button"
                              className={`qc-icon-button ${user.disabled ? "" : "qc-icon-button--danger"}`}
                              title={user.disabled ? "Enable account" : "Disable account"}
                              aria-label={`${user.disabled ? "Enable" : "Disable"} ${user.username}`}
                              disabled={isMe}
                              onClick={() => toggleDisabled(user)}
                            >
                              {user.disabled ? <CheckCircle2 size={15} /> : <Ban size={15} />}
                            </button>
                          </span>
                        </td>
                      </tr>
                      {resetFor === user.username && (
                        <tr className="qc-admin-table__expand">
                          <td colSpan={9}>
                            <PasswordForm
                              user={user}
                              onDone={(message, failed) => {
                                setResetFor(null);
                                if (message) setState(failed ? { error: message, ok: "" } : { error: "", ok: message });
                              }}
                            />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

/* --------------------------------------------------------------- feedback */

function FeedbackTab() {
  const { data, error, loading, reload } = useApi<Feedback>("/api/feedback/summary");
  return (
    <>
      <LoadState loading={loading && !data} error={error} onRetry={reload} />
      {data && (
        <>
          <section className="qc-kpi-row qc-admin-kpis">
            <Kpi label="Satisfaction" value={percent(data.satisfaction)} hint="thumbs up ÷ all ratings" icon={<ShieldCheck size={16} />} tone="warm" />
            <Kpi label="Thumbs up" value={formatValue(data.up)} hint="helpful answers" icon={<ThumbsUp size={16} />} tone="success" />
            <Kpi label="Thumbs down" value={formatValue(data.down)} hint="answers to review" icon={<ThumbsDown size={16} />} tone="danger" />
          </section>
          <section className="qc-panel-grid qc-admin-grid">
            <article className="qc-tile">
              <header className="qc-tile__head"><h2 className="qc-tile__title"><ThumbsDown size={15} /> Why answers missed</h2></header>
              {Object.keys(data.reasons).length ? (
                <BarList rows={Object.entries(data.reasons).map(([label, value]) => ({ label, value }))} />
              ) : (
                <p className="qc-muted">No thumbs-down reasons yet.</p>
              )}
            </article>
            <article className="qc-tile">
              <header className="qc-tile__head"><h2 className="qc-tile__title"><Activity size={15} /> Ratings by route</h2></header>
              {data.by_route.length ? (
                <ul className="qc-admin-routes">
                  {data.by_route.map((row) => {
                    const total = row.up + row.down || 1;
                    return (
                      <li key={row.route}>
                        <span>{ROUTES[row.route] ?? row.route}</span>
                        <span className="qc-admin-routes__bar" aria-hidden="true">
                          <i className="is-up" style={{ width: `${(row.up / total) * 100}%` }} />
                          <i className="is-down" style={{ width: `${(row.down / total) * 100}%` }} />
                        </span>
                        <span className="qc-muted">{row.up} 👍 · {row.down} 👎</span>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="qc-muted">No ratings yet.</p>
              )}
            </article>
          </section>
          <section className="qc-set-card">
            <h3 className="qc-set-card__title">Recent thumbs-down</h3>
            {data.recent_down.length === 0 && <p className="qc-muted">Nothing to review. 🎉</p>}
            <ul className="qc-admin-feed">
              {data.recent_down.map((item) => (
                <li key={`${item.at}-${item.username}`}>
                  <header>
                    <strong>{item.question || "(no question)"}</strong>
                    <span className="qc-muted">@{item.username} · {relative(item.at)}{item.route ? ` · ${ROUTES[item.route] ?? item.route}` : ""}</span>
                  </header>
                  {(item.reasons.length > 0 || item.comment) && (
                    <p>
                      {item.reasons.map((reason) => <span key={reason} className="qc-pill qc-admin-reason">{reason.replace(/_/g, " ")}</span>)}
                      {item.comment && <q>{item.comment}</q>}
                    </p>
                  )}
                  {item.query != null && (
                    <details>
                      <summary>Query that ran{item.trace_id ? ` · trace ${item.trace_id.slice(0, 8)}` : ""}</summary>
                      <pre className="qc-code">{JSON.stringify(item.query, null, 2)}</pre>
                    </details>
                  )}
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </>
  );
}

/* --------------------------------------------------------------- activity */

const ACTIONS: Record<string, string> = {
  "user.create": "created",
  "user.update": "updated",
  "user.password_reset": "set a new password for",
  "user.sessions_revoke": "signed out",
};

function describe(details: Record<string, unknown>) {
  return Object.entries(details)
    .map(([key, value]) => `${key.replace(/_/g, " ")}: ${typeof value === "boolean" ? (value ? "yes" : "no") : String(value)}`)
    .join(" · ");
}

function ActivityTab() {
  const { data, error, loading, reload } = useApi<Audit>("/api/admin/audit");
  return (
    <section className="qc-set-card">
      <LoadState loading={loading && !data} error={error} onRetry={reload} />
      {data && data.events.length === 0 && <p className="qc-muted">No admin actions yet. Changes you make to users show up here.</p>}
      {data && data.events.length > 0 && (
        <ol className="qc-admin-timeline">
          {data.events.map((event, index) => (
            <li key={`${event.at}-${index}`}>
              <span className="qc-admin-timeline__dot" aria-hidden="true" />
              <div>
                <p><b>@{event.actor}</b> {ACTIONS[event.action] ?? event.action} <b>@{event.target}</b></p>
                <span className="qc-muted">{relative(event.at)}{Object.keys(event.details).length ? ` · ${describe(event.details)}` : ""}</span>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

/* ----------------------------------------------------------------- system */

function SystemTab({ data }: { data: Overview }) {
  const s = data.system;
  const checks: { label: string; ok: boolean; detail: string; optional?: boolean }[] = [
    { label: "MongoDB", ok: s.mongodb, detail: s.mongodb ? "Connected" : "Not reachable" },
    { label: "OpenRouter key", ok: s.openrouter_configured, detail: s.openrouter_configured ? `Default model ${s.default_model}` : "OPENROUTER_API_KEY is missing" },
    { label: "Secure cookies", ok: s.cookie_secure, detail: s.cookie_secure ? "COOKIE_SECURE is on" : "Turn on COOKIE_SECURE behind HTTPS" },
    { label: "Jev routing", ok: s.jev_enabled, detail: s.jev_enabled ? "Enabled" : "LangChain classifier only", optional: true },
    { label: "Graphiti knowledge graph", ok: s.graphiti_enabled, detail: s.graphiti_enabled ? "Enabled" : "Off", optional: true },
    { label: "Langfuse tracing", ok: s.langfuse_enabled, detail: s.langfuse_enabled ? "Sending traces" : "Off", optional: true },
    { label: "Self-service sign-up", ok: s.signup_enabled, detail: s.signup_enabled ? "Anyone can create an account" : "Admins create accounts", optional: true },
    { label: "Plan limits", ok: s.plan_limits_enforced, detail: s.plan_limits_enforced ? "Daily limits enforced" : "Unlimited for everyone", optional: true },
  ];
  const live = data.live;
  return (
    <>
      <section className="qc-kpi-row qc-admin-kpis">
        <Kpi label="Requests" value={formatValue(live.requests)} hint="since the server started" icon={<Activity size={16} />} />
        <Kpi label="Median latency" value={seconds(live.latency_p50_s)} hint={`p95 ${seconds(live.latency_p95_s)}`} icon={<RefreshCw size={16} />} />
        <Kpi
          label="Success rate"
          value={live.requests ? `${Math.round(((live.requests - live.errors) / live.requests) * 100)}%` : "—"}
          hint={`${live.errors} errors · ${live.fallbacks} fallbacks`}
          icon={<CheckCircle2 size={16} />}
          tone="success"
        />
        <Kpi label="Signed-in sessions" value={formatValue(data.kpis.active_sessions)} hint="across all devices" icon={<CircleDot size={16} />} />
      </section>
      <section className="qc-set-card">
        <h3 className="qc-set-card__title">Service health</h3>
        <ul className="qc-admin-checks">
          {checks.map((check) => (
            <li key={check.label} className={check.ok ? "is-ok" : check.optional ? "is-off" : "is-bad"}>
              {check.ok ? <CheckCircle2 size={16} /> : check.optional ? <CircleDot size={16} /> : <XCircle size={16} />}
              <strong>{check.label}</strong>
              <span>{check.detail}</span>
            </li>
          ))}
        </ul>
      </section>
      {Object.keys(live.by_route).length > 0 && (
        <section className="qc-tile">
          <h2 className="qc-tile__title">Recent questions by route</h2>
          <BarList rows={Object.entries(live.by_route).map(([route, value]) => ({ label: ROUTES[route] ?? route, value }))} />
        </section>
      )}
    </>
  );
}

/* ------------------------------------------------------------------- page */

export function AdminPage({ isAdmin }: { isAdmin: boolean }) {
  const [tab, setTab] = useState<TabId>("overview");
  const overview = useApi<Overview>(isAdmin ? "/api/admin/overview" : null);

  if (!isAdmin) {
    return (
      <ToolPage icon={<ShieldCheck size={13} />} eyebrow="Admin console" title="Administrators only">
        <div className="qc-state qc-state--error" role="alert">
          <ShieldCheck size={18} /> <span>You need an administrator account to open the admin console.</span>
        </div>
      </ToolPage>
    );
  }

  return (
    <ToolPage
      icon={<ShieldCheck size={13} />}
      eyebrow="Admin console"
      title="Workspace administration"
      description="People, usage, answer quality and service health for the whole workspace, in one place."
      actions={
        <button type="button" className="qc-ghost-button" onClick={overview.reload}>
          <RefreshCw size={13} /> Refresh
        </button>
      }
    >
      <div className="qc-settings qc-admin">
        <nav className="qc-settings__tabs" aria-label="Admin sections" role="tablist">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={tab === item.id}
              className={tab === item.id ? "is-active" : ""}
              onClick={() => setTab(item.id)}
            >
              {item.icon} {item.label}
            </button>
          ))}
        </nav>
        <div className="qc-settings__panel" role="tabpanel">
          {(tab === "overview" || tab === "system") && (
            <LoadState loading={overview.loading && !overview.data} error={overview.error} onRetry={overview.reload} />
          )}
          {tab === "overview" && overview.data && <OverviewTab data={overview.data} />}
          {tab === "system" && overview.data && <SystemTab data={overview.data} />}
          {tab === "users" && <UsersTab />}
          {tab === "feedback" && <FeedbackTab />}
          {tab === "activity" && <ActivityTab />}
        </div>
      </div>
    </ToolPage>
  );
}
