import type { components } from "@inkforge/api-client";
import { browserApi } from "@/lib/api/browser";
import { ApiResponseError, requireApiData } from "@/lib/api/response";
import type { DraftWrite, PendingScriptDraft } from "./script-draft-coordinator";
import { reconcileScriptNodeIds } from "./script-document-state";
import type { ScriptDraft, ScriptDocument } from "./types";

type Schemas = components["schemas"];
export type EpisodeCommand =
  | { kind: "bind-sources"; body: Schemas["SaveVideoEpisodeScriptDraftRequest"] }
  | { kind: "sources"; body: Schemas["CreateVideoEpisodeSourceSetRequest"] }
  | { kind: "rename"; body: Schemas["UpdateVideoEpisodeRequest"] }
  | { kind: "run"; body: Schemas["StartVideoEpisodeScriptRunRequest"] }
  | { kind: "adopt"; artifactId: string; body: Schemas["AdoptVideoEpisodeScriptCandidateRequest"] }
  | { kind: "prepare"; body: Schemas["PrepareVideoEpisodeScriptConfirmationRequest"] }
  | { kind: "approve"; artifactId: string; body: Schemas["ApproveVideoEpisodeScriptConfirmationRequest"] };
export type ProjectCommand =
  | { kind: "create"; body: Schemas["CreateVideoEpisodeRequest"] }
  | { kind: "reorder"; body: Schemas["ReorderVideoEpisodesRequest"] };
export type PendingRunCancellation = { runId: string; clientRequestId: string };

export const getEpisode = async (episodeId: string, signal?: AbortSignal) => requireApiData(await browserApi.GET("/api/v1/video/episodes/{episode_id}", { params: { path: { episode_id: episodeId } }, signal }));
export const getEpisodes = async (projectId: string, signal?: AbortSignal) => requireApiData(await browserApi.GET("/api/v1/video/projects/{project_id}/episodes", { params: { path: { project_id: projectId } }, signal }));

export const cancelScriptRun = async ({ runId, clientRequestId }: PendingRunCancellation) => requireApiData(await browserApi.POST("/api/v1/writing/runs/{task_id}/cancel", {
  params: { path: { task_id: runId } },
  body: { clientRequestId },
}));

async function checkEpisodeReceipt(episodeId: string, requestId: string): Promise<Schemas["VideoEpisodeCommandResponse"] | null> {
  const response = await browserApi.GET("/api/v1/video/episodes/{episode_id}/commands/{client_request_id}", { params: { path: { episode_id: episodeId, client_request_id: requestId } } });
  return response.response.status === 404 ? null : requireApiData(response);
}

export function commandResultIsUnknown(error: unknown): boolean {
  return !(error instanceof ApiResponseError) || error.status >= 500;
}

export async function executeEpisodeCommand(episodeId: string, command: EpisodeCommand, recovering = false) {
  const path = { episode_id: episodeId };
  const receipt = recovering ? await checkEpisodeReceipt(episodeId, command.body.clientRequestId) : null;
  if (receipt) {
    switch (command.kind) {
      case "bind-sources":
      case "adopt":
        return { kind: command.kind, data: requireApiData(await browserApi.GET("/api/v1/video/episodes/{episode_id}/script/draft", { params: { path } })) } as const;
      case "sources":
        return { kind: command.kind, data: requireApiData(await browserApi.GET("/api/v1/video/episodes/{episode_id}/source-sets/{version_id}", { params: { path: { ...path, version_id: receipt.resultId } } })) } as const;
      case "rename":
        return { kind: command.kind, data: (await getEpisode(episodeId)).episode } as const;
      case "run":
        return { kind: command.kind, data: requireApiData(await browserApi.GET("/api/v1/video/episodes/{episode_id}/script/runs/{run_id}", { params: { path: { ...path, run_id: receipt.resultId } } })) } as const;
      case "prepare":
        return { kind: command.kind, data: requireApiData(await browserApi.GET("/api/v1/video/episodes/{episode_id}/script/confirmations/{artifact_id}", { params: { path: { ...path, artifact_id: receipt.resultId } } })) } as const;
      case "approve":
        return { kind: command.kind, data: requireApiData(await browserApi.GET("/api/v1/video/episodes/{episode_id}/script/versions/{version_id}", { params: { path: { ...path, version_id: receipt.resultId } } })) } as const;
    }
  }
  switch (command.kind) {
    case "bind-sources": return { kind: command.kind, data: requireApiData(await browserApi.PUT("/api/v1/video/episodes/{episode_id}/script/draft", { params: { path }, body: command.body })) } as const;
    case "sources": return { kind: command.kind, data: requireApiData(await browserApi.POST("/api/v1/video/episodes/{episode_id}/source-sets", { params: { path }, body: command.body })) } as const;
    case "rename": return { kind: command.kind, data: requireApiData(await browserApi.PATCH("/api/v1/video/episodes/{episode_id}", { params: { path }, body: command.body })) } as const;
    case "run": return { kind: command.kind, data: requireApiData(await browserApi.POST("/api/v1/video/episodes/{episode_id}/script/runs", { params: { path }, body: command.body })) } as const;
    case "adopt": return { kind: command.kind, data: requireApiData(await browserApi.POST("/api/v1/video/episodes/{episode_id}/script/candidates/{artifact_id}/adopt", { params: { path: { ...path, artifact_id: command.artifactId } }, body: command.body })) } as const;
    case "prepare": return { kind: command.kind, data: requireApiData(await browserApi.POST("/api/v1/video/episodes/{episode_id}/script/confirmations", { params: { path }, body: command.body })) } as const;
    case "approve": return { kind: command.kind, data: requireApiData(await browserApi.POST("/api/v1/video/episodes/{episode_id}/script/confirmations/{artifact_id}/approve", { params: { path: { ...path, artifact_id: command.artifactId } }, body: command.body })) } as const;
  }
}

export async function executeProjectCommand(projectId: string, command: ProjectCommand, recovering = false) {
  if (recovering) {
    const receipt = await browserApi.GET("/api/v1/video/projects/{project_id}/episode-commands/{client_request_id}", { params: { path: { project_id: projectId, client_request_id: command.body.clientRequestId } } });
    if (receipt.response.status !== 404) {
      const completed = requireApiData(receipt);
      const episodes = await getEpisodes(projectId);
      if (command.kind === "reorder") return { kind: "reorder", data: episodes } as const;
      const created = episodes.episodes.find((episode) => episode.id === completed.resultId);
      if (!created) throw new Error("分集创建回执存在，但权威分集读取缺失");
      return { kind: "create", data: created } as const;
    }
  }
  return command.kind === "create"
    ? { kind: "create", data: requireApiData(await browserApi.POST("/api/v1/video/projects/{project_id}/episodes", { params: { path: { project_id: projectId } }, body: command.body })) } as const
    : { kind: "reorder", data: requireApiData(await browserApi.POST("/api/v1/video/projects/{project_id}/episodes/reorder", { params: { path: { project_id: projectId } }, body: command.body })) } as const;
}

export async function saveScriptDraft(episodeId: string, baseline: Pick<ScriptDraft, "sourceSetVersionId" | "baseScriptVersionId">, write: DraftWrite<ScriptDocument>, recovering: boolean) {
  const receipt = recovering ? await checkEpisodeReceipt(episodeId, write.clientRequestId) : null;
  const draft = receipt
    ? requireApiData(await browserApi.GET("/api/v1/video/episodes/{episode_id}/script/draft", { params: { path: { episode_id: episodeId } } }))
    : requireApiData(await browserApi.PUT("/api/v1/video/episodes/{episode_id}/script/draft", { params: { path: { episode_id: episodeId } }, body: { clientRequestId: write.clientRequestId, expectedRevision: write.revision, sourceSetVersionId: baseline.sourceSetVersionId, baseScriptVersionId: baseline.baseScriptVersionId, document: write.document } }));
  return { document: draft.document, revision: draft.revision, draft, reconcileLocal: (latest: ScriptDocument) => reconcileScriptNodeIds(latest, draft.nodeIdMappings ?? {}) };
}

export function loadLocalDraft<T>(key: string): T | null {
  try { const raw = localStorage.getItem(key); return raw ? JSON.parse(raw) as T : null; } catch { return null; }
}

export function loadPendingScriptDraft(key: string): PendingScriptDraft<ScriptDocument> | null {
  const stored = loadLocalDraft<PendingScriptDraft<ScriptDocument>>(key);
  if (!stored || typeof stored !== "object" || !stored.baseline || typeof stored.baseline.revision !== "number" || !stored.latest || stored.latest.schemaVersion !== "video-episode-script/1.0" || !stored.baseline.document) return null;
  if (stored.pending && (typeof stored.pending.clientRequestId !== "string" || typeof stored.pending.revision !== "number" || !stored.pending.document)) return null;
  return stored;
}

export function loadPendingEpisodeCommand(key: string): EpisodeCommand | null {
  const stored = loadLocalDraft<EpisodeCommand>(key);
  return stored && ["bind-sources", "sources", "rename", "run", "adopt", "prepare", "approve"].includes(stored.kind) && typeof stored.body?.clientRequestId === "string" ? stored : null;
}

export function loadPendingProjectCommand(key: string): ProjectCommand | null {
  const stored = loadLocalDraft<ProjectCommand>(key);
  return stored && ["create", "reorder"].includes(stored.kind) && typeof stored.body?.clientRequestId === "string" ? stored : null;
}

export function loadPendingRunCancellation(key: string): PendingRunCancellation | null {
  const stored = loadLocalDraft<PendingRunCancellation>(key);
  return stored && typeof stored.runId === "string" && stored.runId.length > 0 && typeof stored.clientRequestId === "string" && stored.clientRequestId.length > 0 ? stored : null;
}
export function saveLocalDraft(key: string, value: unknown): void {
  try { if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, JSON.stringify(value)); } catch { /* Core 写入不依赖浏览器备份。 */ }
}
