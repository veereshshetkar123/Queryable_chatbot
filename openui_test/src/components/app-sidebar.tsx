"use client";

import { useEffect } from "react";
import { AgentInterface, useNav } from "@openuidev/react-ui";
import {
  BookOpen,
  ChevronDown,
  Database,
  Globe2,
  Lightbulb,
  LogOut,
  Moon,
  Network,
  Orbit,
  Plug,
  Search,
  Settings,
  ShieldCheck,
  Sun,
} from "lucide-react";

import { logout, type SessionUser } from "@/lib/api";
import { useLocalStorage } from "@/lib/use-browser";

/** Tool pages, each rendered by an <AgentInterface.Route> in cloud-chat.tsx. */
export const TOOL_ROUTES = {
  search: "search",
  lab: "lab",
  insights: "insights",
  geo: "geo",
  catalog: "catalog",
  prompts: "prompts",
  settings: "settings",
  admin: "admin",
  agents: "agents",
  integrations: "integrations",
} as const;

const TOOLS = [
  { path: TOOL_ROUTES.lab, label: "Analytics lab", icon: <Orbit size={16} />, badge: "New" },
  { path: TOOL_ROUTES.insights, label: "Insights studio", icon: <Lightbulb size={16} /> },
  { path: TOOL_ROUTES.geo, label: "Geo explorer", icon: <Globe2 size={16} />, badge: "New" },
];

/** Admin-only pages; users get these later (see the user view on the roadmap). */
const ADMIN_TOOLS = [
  { path: TOOL_ROUTES.admin, label: "Admin console", icon: <ShieldCheck size={16} /> },
  { path: TOOL_ROUTES.catalog, label: "Data catalog", icon: <Database size={16} /> },
  { path: TOOL_ROUTES.prompts, label: "Prompt library", icon: <BookOpen size={16} /> },
  { path: TOOL_ROUTES.agents, label: "Agent map", icon: <Network size={16} />, badge: "New" },
  { path: TOOL_ROUTES.integrations, label: "Integrations", icon: <Plug size={16} />, badge: "New" },
];

/** Gear button that opens Settings (sidebar footer and mobile header). */
export function SettingsButton({ className = "qc-icon-button" }: { className?: string }) {
  const { navigate } = useNav();
  return (
    <button
      type="button"
      className={className}
      onClick={(event) => {
        event.stopPropagation();
        navigate(TOOL_ROUTES.settings);
      }}
      aria-label="Settings"
      title="Settings"
    >
      <Settings size={15} />
    </button>
  );
}

/**
 * A labelled sidebar group whose items can be folded away; the open/closed
 * state is remembered per browser. In the collapsed (icon-only) sidebar the
 * label is hidden and the items always show.
 */
function SideSection({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  const [stored, setStored] = useLocalStorage(`queryable-side-${id}`);
  const open = stored !== "closed";
  return (
    <nav className="qc-side-section" aria-label={label} data-open={open}>
      <button
        type="button"
        className="qc-side-label qc-side-label--toggle"
        aria-expanded={open}
        onClick={(event) => {
          event.stopPropagation();
          setStored(open ? "closed" : "open");
        }}
      >
        {label}
        <ChevronDown size={12} aria-hidden="true" />
      </button>
      <div className="qc-side-section__items">{children}</div>
    </nav>
  );
}

function SearchShortcut() {
  const { navigate } = useNav();
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        navigate(TOOL_ROUTES.search);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);
  return null;
}

/**
 * ChatGPT/Claude-style sidebar: brand header, New chat + Search, a Tools
 * section, recent conversations, and the signed-in user at the bottom.
 * Built from OpenUI's own sidebar parts, so collapse, mobile drawer and
 * tooltips keep working. Called as a function (not <AppSidebar/>) because
 * AgentInterface finds its slots by the type of its direct children.
 */
export function renderSidebar({
  user,
  mode,
  onToggleTheme,
}: {
  user: SessionUser | null;
  mode: "light" | "dark";
  onToggleTheme: () => void;
}) {
  return (
    <AgentInterface.Sidebar>
      <SearchShortcut />
      <div className="openui-agent-sidebar-actions">
        <AgentInterface.SidebarHeader />
        <div className="openui-agent-sidebar-primary-actions qc-side-primary">
          <AgentInterface.NewChatButton />
          <AgentInterface.SidebarItem
            icon={<Search size={16} />}
            path={TOOL_ROUTES.search}
            trailing={<kbd className="qc-kbd">Ctrl K</kbd>}
          >
            Search chats
          </AgentInterface.SidebarItem>
        </div>
      </div>

      <SideSection id="tools" label="Tools">
        {TOOLS.map((tool) => (
          <AgentInterface.SidebarItem
            key={tool.path}
            icon={tool.icon}
            path={tool.path}
            trailing={tool.badge ? <span className="qc-side-badge">{tool.badge}</span> : undefined}
          >
            {tool.label}
          </AgentInterface.SidebarItem>
        ))}
      </SideSection>

      {/* Saved charts, maps and queries from every answer (lib/artifact-storage.ts). */}
      <SideSection id="artifacts" label="Artifacts">
        <AgentInterface.ArtifactNav className="qc-side-artifacts" />
      </SideSection>

      {user?.role === "admin" && (
        <SideSection id="admin" label="Admin">
          {ADMIN_TOOLS.map((tool) => (
            <AgentInterface.SidebarItem
              key={tool.path}
              icon={tool.icon}
              path={tool.path}
              trailing={tool.badge ? <span className="qc-side-badge qc-side-badge--admin">{tool.badge}</span> : undefined}
            >
              {tool.label}
            </AgentInterface.SidebarItem>
          ))}
        </SideSection>
      )}

      <AgentInterface.SidebarContent className="qc-side-recents">
        <AgentInterface.ThreadList />
      </AgentInterface.SidebarContent>

      {user && (
        <div className="qc-side-user">
          <span className="qc-side-user__avatar" aria-hidden="true">
            {user.display_name.slice(0, 1).toUpperCase()}
          </span>
          <span className="qc-side-user__text">
            <strong>{user.display_name}</strong>
            <span>
              {user.role === "admin"
                ? "Administrator"
                : user.plan
                  ? `${user.plan.charAt(0).toUpperCase()}${user.plan.slice(1)} plan`
                  : "Analyst"}
            </span>
          </span>
          <SettingsButton className="qc-side-user__action" />
          <button
            type="button"
            className="qc-side-user__action"
            onClick={(event) => {
              event.stopPropagation();
              onToggleTheme();
            }}
            aria-label={`Switch to ${mode === "dark" ? "light" : "dark"} mode`}
            title={`Switch to ${mode === "dark" ? "light" : "dark"} mode`}
          >
            {mode === "dark" ? <Sun size={15} /> : <Moon size={15} />}
          </button>
          <button
            type="button"
            className="qc-side-user__action"
            onClick={(event) => {
              event.stopPropagation();
              void logout();
            }}
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut size={15} />
          </button>
        </div>
      )}
    </AgentInterface.Sidebar>
  );
}
