"use client";

import { usePersistedModel } from "@/hooks/use-persisted-model";
import { MODEL_OPTIONS } from "@/lib/models";
import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import {
  OPENUI_LOGOS,
  PROMPT_TEMPLATES,
  STARTERS,
} from "@/lib/starters";

import {
  AgentInterface,
  ModelSwitcher,
  fetchLLM,
  openuiLibrary,
  openAIConversationMessageFormat,
  openAIResponsesAdapter,
  useOpenuiCloudStorage,
  useSystemThemeMode,
} from "@openuidev/react-ui";

export default function CloudChat() {
  const systemMode = useSystemThemeMode();
  const [themeOverride, setThemeOverride] = useState<"dark" | "light" | null>(null);
  const mode = themeOverride ?? systemMode;

  useEffect(() => {
    const savedTheme = window.localStorage.getItem("queryable-chat-theme");
    if (savedTheme === "dark" || savedTheme === "light") {
      setThemeOverride(savedTheme);
    }
  }, []);

  const [selectedModel, setSelectedModel] =
    usePersistedModel();

  const llm = fetchLLM({
    url: "/api/chat",
    streamAdapter: openAIResponsesAdapter(),
    messageFormat: openAIConversationMessageFormat,
    body: {
      model: selectedModel,
    },
  });

  const storage = useOpenuiCloudStorage({
    token: "/api/frontend-token",
    apiBaseUrl: "https://api.thesys.dev",
    features: {
      artifact: false,
    },
  });

  const logoPath =
    mode === "dark"
      ? OPENUI_LOGOS.DARK
      : OPENUI_LOGOS.LIGHT;

  return (
    <div className="cinematic-chatbot" data-theme={mode}>

      {/* Cinematic background atmosphere */}
      <div className="cinematic-background">
        <div className="cinematic-glow cinematic-glow-one" />
        <div className="cinematic-glow cinematic-glow-two" />
        <div className="cinematic-grid" />
      </div>

      <button
        className="cinematic-theme-toggle"
        type="button"
        aria-label={`Switch to ${mode === "dark" ? "light" : "dark"} mode`}
        title={`Switch to ${mode === "dark" ? "light" : "dark"} mode`}
        onClick={() => {
          const nextTheme = mode === "dark" ? "light" : "dark";
          setThemeOverride(nextTheme);
          window.localStorage.setItem("queryable-chat-theme", nextTheme);
        }}
      >
        {mode === "dark" ? <Sun size={18} /> : <Moon size={18} />}
      </button>

      {/* OpenUI */}
      <div className="cinematic-interface">
        <AgentInterface
          storage={storage}
          llm={llm}
          componentLibrary={openuiLibrary}
          logoUrl={logoPath}
          theme={{ mode }}
          starters={STARTERS}
        >
          <AgentInterface.MobileHeader
            agentName=""
            actions={
              <ModelSwitcher
                models={MODEL_OPTIONS}
                value={selectedModel}
                onValueChange={setSelectedModel}
              />
            }
          />

          <AgentInterface.ThreadHeader className="openui-cloud-thread-header">
            <ModelSwitcher
              models={MODEL_OPTIONS}
              value={selectedModel}
              onValueChange={setSelectedModel}
            />
          </AgentInterface.ThreadHeader>

          <AgentInterface.Welcome
            title="Good to see you"
            description="Ask anything about your data."
            promptTemplates={PROMPT_TEMPLATES}
            glowAnimation
          />
        </AgentInterface>
      </div>

    </div>
  );
}