import type { Artifact, ArtifactListParams, ArtifactStorage, ArtifactSummary } from "@openuidev/react-headless";

import { authFetch, errorMessage } from "@/lib/api";

/**
 * OpenUI ArtifactStorage backed by FastAPI's /api/artifacts (backend/artifacts.py).
 * Powers the sidebar "Artifacts" library: every chart, map, insight set and
 * query an answer produced is saved per user and can be reopened later.
 */
export function artifactStorage(baseUrl = "/api/artifacts"): ArtifactStorage {
  const request = async <T>(url: string, init?: RequestInit): Promise<T> => {
    const response = await authFetch(url, init);
    if (!response.ok) throw new Error(await errorMessage(response, "The artifact request failed."));
    return (await response.json()) as T;
  };

  return {
    list(params: ArtifactListParams = {}) {
      const query = new URLSearchParams();
      if (params.name) query.set("name", params.name);
      if (params.type?.length) query.set("type", params.type.join(","));
      if (params.cursor) query.set("cursor", params.cursor);
      if (params.limit) query.set("limit", String(params.limit));
      const suffix = query.toString();
      return request<{ artifacts: ArtifactSummary[]; nextCursor?: string }>(suffix ? `${baseUrl}?${suffix}` : baseUrl);
    },
    get(id: string) {
      return request<Artifact>(`${baseUrl}/${encodeURIComponent(id)}`);
    },
    update(patch: { id: string; content: unknown }) {
      return request<ArtifactSummary>(`${baseUrl}/${encodeURIComponent(patch.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: patch.content }),
      });
    },
  };
}
