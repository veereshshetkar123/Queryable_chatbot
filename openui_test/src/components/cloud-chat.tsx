"use client";

import { useEffect, useMemo, useState } from "react";
import { BarChart3, Database, Globe2, LogOut, Moon, Sun } from "lucide-react";
import {
  AgentInterface,
  ModelSwitcher,
  agUIAdapter,
  fetchLLM,
  identityMessageFormat,
  restStorage,
  useSystemThemeMode,
  type ModelOption,
} from "@openuidev/react-ui";
import type { ArtifactCategory } from "@openuidev/react-headless";
import { openuiChatLibrary } from "@openuidev/react-ui/genui-lib";

import { dataInsightsRenderer, geoMapRenderer, visualAnalysisRenderer } from "@/components/analysis-renderers";
import { QueryableAssistantMessage } from "@/components/assistant-message";
import { renderSidebar, SettingsButton, TOOL_ROUTES } from "@/components/app-sidebar";
import { artifactRenderers as queryRenderers } from "@/components/query-inspector";
import { AdminOnly, ChatFileDrop } from "@/components/admin-only";
import { AdminPage } from "@/components/tools/admin-page";
import { AgentMapPage } from "@/components/tools/agent-map-page";
import { IntegrationsPage } from "@/components/tools/integrations-page";
import { AnalyticsLabPage } from "@/components/tools/analytics-lab-page";
import { CatalogPage } from "@/components/tools/catalog-page";
import { GeoExplorerPage } from "@/components/tools/geo-explorer-page";
import { InsightsPage } from "@/components/tools/insights-page";
import { PromptsPage } from "@/components/tools/prompts-page";
import { SearchPage } from "@/components/tools/search-page";
import { SettingsPage } from "@/components/tools/settings-page";
import { Backdrop } from "@/components/backdrop";
import { VoiceDock } from "@/components/voice-dock";
import { useLocalStorage } from "@/lib/use-browser";
import { authFetch, fetchCurrentUser, logout, type SessionUser } from "@/lib/api";
import { artifactStorage } from "@/lib/artifact-storage";
import { queryableDarkTheme, queryableLightTheme } from "@/lib/theme";
import { BRAND_LOGOS, PROMPT_TEMPLATES, STARTERS } from "@/lib/starters";

const MODEL_STORAGE_KEY = "queryable-chat-model";

// Captured once at mount by ChatProvider, so it must be a stable module constant.
const artifactRenderers = [...queryRenderers, geoMapRenderer, visualAnalysisRenderer, dataInsightsRenderer];
// Sidebar "Artifacts" library: each category is one nav item and one section
// of the per-conversation workspace rail. Types match the renderers above and
// backend/artifacts.py TOOL_TYPES.
const artifactCategories: ArtifactCategory[] = [
  { name: "Charts & insights", filter: { type: ["qc_visual_analysis", "qc_data_insights"] }, icon: <BarChart3 size={16} /> },
  { name: "Maps", filter: { type: ["qc_geo_map"] }, icon: <Globe2 size={16} /> },
  { name: "Queries", filter: { type: ["qc_mongodb_query"] }, icon: <Database size={16} /> },
];
const labels = { defaultCategory: "Artifacts", workspaceToggle: "Artifacts in this chat" };
// Answers with a thumbs up / down bar (see assistant-message.tsx).
const components = { AssistantMessage: QueryableAssistantMessage };

const PROVIDER_GROUPS: Record<string, string> = {
  google: "Google",
  openai: "OpenAI",
  anthropic: "Anthropic",
};

function toModelOptions(ids: string[]): ModelOption[] {
  return ids.map((id) => {
    const [provider, name] = id.split("/");
    const group = PROVIDER_GROUPS[provider] ?? provider;
    const logo =
      provider in PROVIDER_GROUPS
        ? {
            light: <img src={`/logos/${provider}-light.svg`} alt="" />,
            dark: <img src={`/logos/${provider}-dark.svg`} alt="" />,
          }
        : undefined;
    return { id, name: name ?? id, group, logo };
  });
}

/**
 * The one Queryable Chatbot interface: OpenUI's AgentInterface inside the
 * Queryable shell. Messages go to FastAPI (/api/chat, AG-UI stream), threads
 * are stored per user in MongoDB (/api/threads), and assistant messages are
 * OpenUI Lang rendered with the official openuiChatLibrary.
 */
export default function CloudChat() {
  const systemMode = useSystemThemeMode();
  const [savedTheme, setSavedTheme] = useLocalStorage("queryable-chat-theme");
  const mode = savedTheme === "dark" || savedTheme === "light" ? savedTheme : systemMode;

  const [user, setUser] = useState<SessionUser | null>(null);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [defaultModel, setDefaultModel] = useState<string>("");
  const [savedModel, setSavedModel] = useLocalStorage(MODEL_STORAGE_KEY);
  const modelIds = models.map((model) => model.id);
  const selectedModel = savedModel && modelIds.includes(savedModel) ? savedModel : defaultModel;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const current = await fetchCurrentUser();
      if (!current) {
        window.location.assign("/login?expired=1");
        return;
      }
      if (cancelled) return;
      setUser(current);

      const response = await authFetch("/api/models");
      if (!response.ok || cancelled) return;
      const data = (await response.json()) as { default: string; models: string[] };
      setModels(toModelOptions(data.models));
      setDefaultModel(data.default);
    })();

    // Re-check the session when the tab regains focus (idle expiry, logout elsewhere).
    const onFocus = () => {
      void fetchCurrentUser().then((current) => {
        if (!current) window.location.assign("/login?expired=1");
      });
    };
    window.addEventListener("focus", onFocus);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", onFocus);
    };
  }, []);

  const chooseModel = (model: string) => setSavedModel(model);
  const role = user ? user.role : null;

  const llm = useMemo(
    () =>
      fetchLLM({
        url: "/api/chat",
        streamAdapter: agUIAdapter(),
        messageFormat: identityMessageFormat,
        fetch: authFetch,
        body: selectedModel ? { model: selectedModel } : {},
      }),
    [selectedModel],
  );

  const storage = useMemo(
    () => ({ ...restStorage({ baseUrl: "/api/threads", fetch: authFetch }), artifact: artifactStorage() }),
    [],
  );

  const logoPath = mode === "dark" ? BRAND_LOGOS.DARK : BRAND_LOGOS.LIGHT;

  const modelSwitcher =
    models.length > 0 && selectedModel ? (
      <ModelSwitcher models={models} value={selectedModel} onValueChange={chooseModel} />
    ) : null;

  const nextMode = mode === "dark" ? "light" : "dark";
  const themeToggle = (
    <button
      className="qc-icon-button"
      type="button"
      aria-label={`Switch to ${nextMode} mode`}
      title={`Switch to ${nextMode} mode`}
      onClick={() => setSavedTheme(nextMode)}
    >
      {mode === "dark" ? <Sun size={17} /> : <Moon size={17} />}
    </button>
  );

  const userMenu = user ? (
    <div className="qc-user">
      <span className="qc-user__avatar" aria-hidden="true">
        {user.display_name.slice(0, 1).toUpperCase()}
      </span>
      <span className="qc-user__name">{user.display_name}</span>
      <button type="button" className="qc-user__logout" onClick={() => void logout()} aria-label="Sign out" title="Sign out">
        <LogOut size={15} />
      </button>
    </div>
  ) : null;

  // Desktop shows the user in the sidebar footer; mobile keeps it in the header.
  const headerTools = <div className="qc-header-tools">{themeToggle}</div>;
  const mobileTools = (
    <div className="qc-header-tools">
      {themeToggle}
      <SettingsButton />
      {userMenu}
    </div>
  );

  return (
    <div className="qc-app" data-theme={mode}>
      <Backdrop />
      <div className="qc-interface">
        <AgentInterface
          storage={storage}
          llm={llm}
          componentLibrary={openuiChatLibrary}
          components={components}
          artifactRenderers={artifactRenderers}
          artifactCategories={artifactCategories}
          labels={labels}
          logoUrl={logoPath}
          agentName="Queryable Chatbot"
          theme={{ mode, darkTheme: queryableDarkTheme, lightTheme: queryableLightTheme }}
          starters={STARTERS}
          scrollVariant="always"
        >
          {renderSidebar({ user, mode, onToggleTheme: () => setSavedTheme(nextMode) })}

          <AgentInterface.Route path={TOOL_ROUTES.search}>
            <SearchPage />
          </AgentInterface.Route>
          <AgentInterface.Route path={TOOL_ROUTES.lab}>
            <AnalyticsLabPage />
          </AgentInterface.Route>
          <AgentInterface.Route path={TOOL_ROUTES.insights}>
            <InsightsPage />
          </AgentInterface.Route>
          <AgentInterface.Route path={TOOL_ROUTES.geo}>
            <GeoExplorerPage />
          </AgentInterface.Route>
          <AgentInterface.Route path={TOOL_ROUTES.catalog}>
            <AdminOnly role={role}>
              <CatalogPage />
            </AdminOnly>
          </AgentInterface.Route>
          <AgentInterface.Route path={TOOL_ROUTES.prompts}>
            <AdminOnly role={role}>
              <PromptsPage />
            </AdminOnly>
          </AgentInterface.Route>
          <AgentInterface.Route path={TOOL_ROUTES.agents}>
            <AdminOnly role={role}>
              <AgentMapPage />
            </AdminOnly>
          </AgentInterface.Route>
          <AgentInterface.Route path={TOOL_ROUTES.integrations}>
            <AdminOnly role={role}>
              <IntegrationsPage />
            </AdminOnly>
          </AgentInterface.Route>
          <AgentInterface.Route path={TOOL_ROUTES.admin}>
            <AdminPage isAdmin={user?.role === "admin"} />
          </AgentInterface.Route>
          <AgentInterface.Route path={TOOL_ROUTES.settings}>
            <SettingsPage
              theme={savedTheme === "dark" || savedTheme === "light" ? savedTheme : "system"}
              onTheme={setSavedTheme}
              models={models.map(({ id, name, group }) => ({ id, name, group: group ?? "" }))}
              model={selectedModel}
              onModel={chooseModel}
              onUserChange={(patch) => setUser((current) => (current ? { ...current, ...patch } : current))}
            />
          </AgentInterface.Route>

          <AgentInterface.MobileHeader
            agentName="Queryable Chatbot"
            actions={
              <>
                {modelSwitcher}
                {mobileTools}
              </>
            }
          />

          <AgentInterface.ThreadHeader className="qc-thread-header">
            {modelSwitcher}
            {headerTools}
          </AgentInterface.ThreadHeader>

          <AgentInterface.Welcome
            title={user ? `Good to see you, ${user.display_name.split(" ")[0]}` : "Queryable Chatbot"}
            description="Ask about companies, customers, orders, products and sales. Every number comes straight from your MongoDB data."
            promptTemplates={PROMPT_TEMPLATES}
          />

          <VoiceDock />
          <ChatFileDrop enabled={role === "admin"} />
        </AgentInterface>
      </div>
    </div>
  );
}
