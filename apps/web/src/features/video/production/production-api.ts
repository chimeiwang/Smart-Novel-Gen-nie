import type { components } from "@inkforge/api-client";

import { browserApi } from "@/lib/api/browser";
import { requireApiData } from "@/lib/api/response";
import { loadLocalDraft } from "./episode-api";
import type { DraftWrite, PendingScriptDraft } from "./script-draft-coordinator";
import {
  reconcileStoryboardShotIds,
  storyboardDraftFromResponse,
  type StoryboardWorkingDraft,
} from "./storyboard-document-state";
import type { ProductionKeyframeInput } from "./types";

type Schemas = components["schemas"];
type CreateProductionBaselineCommand = Schemas["CreateVideoProductionBaselineRequest"] & {
  keyframes: ProductionKeyframeInput[];
};

export type ProductionCommand =
  | { kind: "storyboard-run"; body: Schemas["StartVideoStoryboardRunRequest"] }
  | { kind: "storyboard-adopt"; artifactId: string; body: Schemas["AdoptVideoStoryboardCandidateRequest"] }
  | { kind: "storyboard-prepare"; body: Schemas["PrepareVideoStoryboardConfirmationRequest"] }
  | { kind: "storyboard-approve"; artifactId: string; body: Schemas["ApproveVideoStoryboardConfirmationRequest"] }
  | { kind: "take-adoption"; body: Schemas["CreateVideoTakeAdoptionRequest"] }
  | { kind: "baseline-create"; body: CreateProductionBaselineCommand };
export type PendingImpactDecision = {
  reviewId: string;
  body: Schemas["DecideVideoImpactReviewRequest"];
};

const episodePath = (episodeId: string) => ({ episode_id: episodeId });

export const getProductionCapabilities = async (signal?: AbortSignal) => requireApiData(await browserApi.GET(
  "/api/v1/video/production-capabilities",
  { signal },
));

export const getStoryboardDraft = async (episodeId: string, signal?: AbortSignal) => requireApiData(await browserApi.GET(
  "/api/v1/video/episodes/{episode_id}/storyboard/draft",
  { params: { path: episodePath(episodeId) }, signal },
));

export const getEpisodeScriptVersion = async (episodeId: string, versionId: string) => requireApiData(await browserApi.GET(
  "/api/v1/video/episodes/{episode_id}/script/versions/{version_id}",
  { params: { path: { ...episodePath(episodeId), version_id: versionId } } },
));

export const getStoryboardConfirmation = async (episodeId: string, artifactId: string) => requireApiData(await browserApi.GET(
  "/api/v1/video/episodes/{episode_id}/storyboard/confirmations/{artifact_id}",
  { params: { path: { ...episodePath(episodeId), artifact_id: artifactId } } },
));

export const listStoryboardRuns = async (episodeId: string, beforeRunId?: string) => requireApiData(await browserApi.GET(
  "/api/v1/video/episodes/{episode_id}/storyboard/runs",
  { params: { path: episodePath(episodeId), query: { limit: 20, beforeRunId } } },
));

export const getStoryboardRun = async (episodeId: string, runId: string, signal?: AbortSignal) => requireApiData(await browserApi.GET(
  "/api/v1/video/episodes/{episode_id}/storyboard/runs/{run_id}",
  { params: { path: { ...episodePath(episodeId), run_id: runId } }, signal },
));

export const getStoryboardCandidate = async (episodeId: string, artifactId: string) => requireApiData(await browserApi.GET(
  "/api/v1/video/episodes/{episode_id}/storyboard/candidates/{artifact_id}",
  { params: { path: { ...episodePath(episodeId), artifact_id: artifactId } } },
));

export const getStoryboardVersion = async (episodeId: string, versionId: string) => requireApiData(await browserApi.GET(
  "/api/v1/video/episodes/{episode_id}/storyboard/versions/{version_id}",
  { params: { path: { ...episodePath(episodeId), version_id: versionId } } },
));

export const listStoryboardVersions = async (episodeId: string, beforeVersionNo?: number) => requireApiData(await browserApi.GET(
  "/api/v1/video/episodes/{episode_id}/storyboard/versions",
  { params: { path: episodePath(episodeId), query: { limit: 20, beforeVersionNo } } },
));

export const getProductionBaseline = async (episodeId: string, baselineId: string) => requireApiData(await browserApi.GET(
  "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}",
  { params: { path: { ...episodePath(episodeId), baseline_id: baselineId } } },
));

export const listProductionBaselines = async (episodeId: string, beforeVersionNo?: number) => requireApiData(await browserApi.GET(
  "/api/v1/video/episodes/{episode_id}/production-baselines",
  { params: { path: episodePath(episodeId), query: { limit: 20, beforeVersionNo } } },
));

export const listTakeCandidates = async (episodeId: string, targetShotVersionId: string, beforeTakeId?: string, limit = 20) => requireApiData(await browserApi.GET(
  "/api/v1/video/episodes/{episode_id}/takes",
  { params: { path: episodePath(episodeId), query: { targetShotVersionId, limit, beforeTakeId } } },
));

export const getTakeAdoption = async (episodeId: string, adoptionId: string) => requireApiData(await browserApi.GET(
  "/api/v1/video/episodes/{episode_id}/take-adoptions/{adoption_id}",
  { params: { path: { ...episodePath(episodeId), adoption_id: adoptionId } } },
));

export const startEpisodeRender = async (episodeId: string, baselineId: string, shotId: string, body: Schemas["StartVideoEpisodeShotRenderRequest"]) => requireApiData(await browserApi.POST(
  "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/shots/{shot_id}/render-tasks",
  { params: { path: { ...episodePath(episodeId), baseline_id: baselineId, shot_id: shotId } }, body },
));

export const getEpisodeRenderTask = async (episodeId: string, taskId: string, signal?: AbortSignal) => requireApiData(await browserApi.GET(
  "/api/v1/video/episodes/{episode_id}/render-tasks/{task_id}",
  { params: { path: { ...episodePath(episodeId), task_id: taskId } }, signal },
));

export const retryEpisodeRender = async (episodeId: string, taskId: string, body: Schemas["RetryVideoEpisodeShotRenderRequest"]) => requireApiData(await browserApi.POST(
  "/api/v1/video/episodes/{episode_id}/render-tasks/{task_id}/retry",
  { params: { path: { ...episodePath(episodeId), task_id: taskId } }, body },
));

export const episodeTakeContentUrl = (episodeId: string, takeId: string) => `/api/v1/video/episodes/${encodeURIComponent(episodeId)}/takes/${encodeURIComponent(takeId)}/content`;

const baselinePath = (episodeId: string, baselineId: string) => ({ ...episodePath(episodeId), baseline_id: baselineId });

export const listEpisodeEditVersions = async (episodeId: string, baselineId: string, beforeVersionNo?: number) => requireApiData(await browserApi.GET(
  "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/edit-versions",
  { params: { path: baselinePath(episodeId, baselineId), query: { limit: 20, beforeVersionNo } } },
));

export const getEpisodeEditVersion = async (episodeId: string, baselineId: string, versionId: string) => requireApiData(await browserApi.GET(
  "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/edit-versions/{version_id}",
  { params: { path: { ...baselinePath(episodeId, baselineId), version_id: versionId } } },
));

export const createEpisodeEditVersion = async (episodeId: string, baselineId: string, body: Schemas["CreateVideoEpisodeEditVersionRequest"]) => requireApiData(await browserApi.POST(
  "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/edit-versions",
  { params: { path: baselinePath(episodeId, baselineId) }, body },
));

export const listEpisodeMixVersions = async (episodeId: string, baselineId: string, beforeVersionNo?: number) => requireApiData(await browserApi.GET(
  "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/mix-versions",
  { params: { path: baselinePath(episodeId, baselineId), query: { limit: 20, beforeVersionNo } } },
));

export const getEpisodeMixVersion = async (episodeId: string, baselineId: string, versionId: string) => requireApiData(await browserApi.GET(
  "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/mix-versions/{version_id}",
  { params: { path: { ...baselinePath(episodeId, baselineId), version_id: versionId } } },
));

export const createEpisodeMixVersion = async (episodeId: string, baselineId: string, body: Schemas["CreateVideoEpisodeMixVersionRequest"]) => requireApiData(await browserApi.POST(
  "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/mix-versions",
  { params: { path: baselinePath(episodeId, baselineId) }, body },
));

export const startEpisodeExport = async (episodeId: string, baselineId: string, body: Schemas["StartVideoEpisodeExportRequest"]) => requireApiData(await browserApi.POST(
  "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/export-tasks",
  { params: { path: baselinePath(episodeId, baselineId) }, body },
));

export const getEpisodeExportTask = async (episodeId: string, baselineId: string, taskId: string, signal?: AbortSignal) => requireApiData(await browserApi.GET(
  "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/export-tasks/{task_id}",
  { params: { path: { ...baselinePath(episodeId, baselineId), task_id: taskId } }, signal },
));

export const retryEpisodeExport = async (episodeId: string, baselineId: string, taskId: string, body: Schemas["RetryVideoEpisodeExportRequest"]) => requireApiData(await browserApi.POST(
  "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/export-tasks/{task_id}/retry",
  { params: { path: { ...baselinePath(episodeId, baselineId), task_id: taskId } }, body },
));

export const episodeDeliveryContentUrl = (episodeId: string, baselineId: string, deliveryId: string) => `/api/v1/video/episodes/${encodeURIComponent(episodeId)}/production-baselines/${encodeURIComponent(baselineId)}/exports/${encodeURIComponent(deliveryId)}/content`;

export const getVideoProject = async (projectId: string) => requireApiData(await browserApi.GET(
  "/api/v1/video/projects/{project_id}",
  { params: { path: { project_id: projectId } } },
));

export async function uploadEpisodeAudioAsset(projectId: string, file: File, duty: "voice" | "ambience" | "sfx" | "music", name: string) {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", await file.arrayBuffer()));
  const sha256 = [...digest].map((value) => value.toString(16).padStart(2, "0")).join("");
  let asset = (await getVideoProject(projectId)).assets.find((item) => item.modality === "audio" && item.duty === duty && item.sha256 === sha256) ?? null;
  if (!asset) {
    try {
      asset = requireApiData(await browserApi.POST(
        "/api/v1/video/projects/{project_id}/assets",
        {
          params: { path: { project_id: projectId } },
          body: { file: file as unknown as string, name, modality: "audio", duty, sourceKind: "user_upload" },
          bodySerializer: () => {
            const body = new FormData();
            body.append("file", file);
            body.append("name", name);
            body.append("modality", "audio");
            body.append("duty", duty);
            body.append("sourceKind", "user_upload");
            return body;
          },
        },
      ));
    } catch (failure) {
      asset = (await getVideoProject(projectId)).assets.find((item) => item.modality === "audio" && item.duty === duty && item.sha256 === sha256) ?? null;
      if (!asset) throw failure;
    }
  }
  return requireApiData(await browserApi.PATCH(
    "/api/v1/video/assets/{asset_id}/rights",
    { params: { path: { asset_id: asset.id } }, body: { rightsStatus: "confirmed" } },
  ));
}

export const listImpactReviews = async (episodeId: string, status: "pending" | "resolved", beforeReviewId?: string) => requireApiData(await browserApi.GET(
  "/api/v1/video/episodes/{episode_id}/impact-reviews",
  { params: { path: episodePath(episodeId), query: { status, limit: 20, beforeReviewId } } },
));

export const getImpactReview = async (episodeId: string, reviewId: string) => requireApiData(await browserApi.GET(
  "/api/v1/video/episodes/{episode_id}/impact-reviews/{review_id}",
  { params: { path: { ...episodePath(episodeId), review_id: reviewId } } },
));

export async function decideImpactReview(
  episodeId: string,
  projectId: string,
  pending: PendingImpactDecision,
  recovering: boolean,
) {
  if (recovering) {
    const receipt = await browserApi.GET(
      "/api/v1/video/projects/{project_id}/episode-commands/{client_request_id}",
      { params: { path: { project_id: projectId, client_request_id: pending.body.clientRequestId } } },
    );
    if (receipt.response.status !== 404) {
      const completed = requireApiData(receipt);
      if (completed.operation !== "episode.impact-review.decide") throw new Error("影响复核请求标识已用于其他操作");
      return getImpactReview(episodeId, pending.reviewId);
    }
  }
  return requireApiData(await browserApi.POST(
    "/api/v1/video/episodes/{episode_id}/impact-reviews/{review_id}/decisions",
    { params: { path: { ...episodePath(episodeId), review_id: pending.reviewId } }, body: pending.body },
  ));
}

async function getCommandReceipt(episodeId: string, clientRequestId: string) {
  const response = await browserApi.GET(
    "/api/v1/video/episodes/{episode_id}/commands/{client_request_id}",
    { params: { path: { ...episodePath(episodeId), client_request_id: clientRequestId } } },
  );
  return response.response.status === 404 ? null : requireApiData(response);
}

export async function saveStoryboardDraft(
  episodeId: string,
  write: DraftWrite<StoryboardWorkingDraft>,
  recovering: boolean,
) {
  const receipt = recovering ? await getCommandReceipt(episodeId, write.clientRequestId) : null;
  if (receipt && receipt.operation !== "episode.storyboard.save") {
    throw new Error("分镜保存请求标识已用于其他操作，请保留本地输入并重新核对");
  }
  const response = receipt
    ? await getStoryboardDraft(episodeId)
    : requireApiData(await browserApi.PUT(
      "/api/v1/video/episodes/{episode_id}/storyboard/draft",
      {
        params: { path: episodePath(episodeId) },
        body: {
          clientRequestId: write.clientRequestId,
          expectedRevision: write.revision,
          scriptVersionId: write.document.scriptVersionId ?? "",
          baseStoryboardVersionId: write.document.baseStoryboardVersionId,
          document: write.document.document,
        },
      },
    ));
  return {
    document: storyboardDraftFromResponse(response),
    revision: response.revision,
    response,
    reconcileLocal: (latest: StoryboardWorkingDraft): StoryboardWorkingDraft => ({
      ...latest,
      document: reconcileStoryboardShotIds(latest.document, response.shotIdMappings ?? {}),
    }),
  };
}

export async function executeProductionCommand(
  episodeId: string,
  command: ProductionCommand,
  recovering = false,
) {
  const path = episodePath(episodeId);
  const receipt = recovering ? await getCommandReceipt(episodeId, command.body.clientRequestId) : null;
  if (receipt) {
    const expectedOperation = {
      "storyboard-run": "episode.storyboard.run",
      "storyboard-adopt": "episode.storyboard.adopt",
      "storyboard-prepare": "episode.storyboard.prepare",
      "storyboard-approve": "episode.storyboard.approve",
      "take-adoption": "episode.take-adoption.create",
      "baseline-create": "episode.production-baseline.create",
    }[command.kind];
    if (receipt.operation !== expectedOperation) throw new Error("制作请求标识已用于其他操作，请重新核对");
    switch (command.kind) {
      case "storyboard-run":
        return { kind: command.kind, data: await getStoryboardRun(episodeId, receipt.resultId) } as const;
      case "storyboard-adopt":
        return { kind: command.kind, data: await getStoryboardDraft(episodeId) } as const;
      case "storyboard-prepare":
        return { kind: command.kind, data: await getStoryboardConfirmation(episodeId, receipt.resultId) } as const;
      case "storyboard-approve":
        return { kind: command.kind, data: await getStoryboardVersion(episodeId, receipt.resultId) } as const;
      case "take-adoption":
        return { kind: command.kind, data: await getTakeAdoption(episodeId, receipt.resultId) } as const;
      case "baseline-create":
        return { kind: command.kind, data: await getProductionBaseline(episodeId, receipt.resultId) } as const;
    }
  }
  switch (command.kind) {
    case "storyboard-run":
      return { kind: command.kind, data: requireApiData(await browserApi.POST(
        "/api/v1/video/episodes/{episode_id}/storyboard/runs",
        { params: { path }, body: command.body },
      )) } as const;
    case "storyboard-adopt":
      return { kind: command.kind, data: requireApiData(await browserApi.POST(
        "/api/v1/video/episodes/{episode_id}/storyboard/candidates/{artifact_id}/adopt",
        { params: { path: { ...path, artifact_id: command.artifactId } }, body: command.body },
      )) } as const;
    case "storyboard-prepare":
      return { kind: command.kind, data: requireApiData(await browserApi.POST(
        "/api/v1/video/episodes/{episode_id}/storyboard/confirmations",
        { params: { path }, body: command.body },
      )) } as const;
    case "storyboard-approve":
      return { kind: command.kind, data: requireApiData(await browserApi.POST(
        "/api/v1/video/episodes/{episode_id}/storyboard/confirmations/{artifact_id}/approve",
        { params: { path: { ...path, artifact_id: command.artifactId } }, body: command.body },
      )) } as const;
    case "take-adoption":
      return { kind: command.kind, data: requireApiData(await browserApi.POST(
        "/api/v1/video/episodes/{episode_id}/take-adoptions",
        { params: { path }, body: command.body },
      )) } as const;
    case "baseline-create":
      return { kind: command.kind, data: requireApiData(await browserApi.POST(
        "/api/v1/video/episodes/{episode_id}/production-baselines",
        { params: { path }, body: command.body },
      )) } as const;
  }
}

export function loadPendingStoryboardDraft(key: string): PendingScriptDraft<StoryboardWorkingDraft> | null {
  const value = loadLocalDraft<PendingScriptDraft<StoryboardWorkingDraft>>(key);
  if (!value?.baseline?.document || !value.latest?.document || typeof value.baseline.revision !== "number") return null;
  if (value.latest.document.schemaVersion !== "video-episode-storyboard/1.0") return null;
  if (value.pending && (typeof value.pending.clientRequestId !== "string" || typeof value.pending.revision !== "number")) return null;
  return value;
}

export function loadPendingProductionCommand(key: string): ProductionCommand | null {
  const value = loadLocalDraft<ProductionCommand>(key);
  if (!value || !["storyboard-run", "storyboard-adopt", "storyboard-prepare", "storyboard-approve", "take-adoption", "baseline-create"].includes(value.kind)) return null;
  return typeof value.body?.clientRequestId === "string" ? value : null;
}

export function loadPendingImpactDecision(key: string): PendingImpactDecision | null {
  const value = loadLocalDraft<PendingImpactDecision>(key);
  return value && typeof value.reviewId === "string" && typeof value.body?.clientRequestId === "string" && Array.isArray(value.body.decisions) ? value : null;
}
