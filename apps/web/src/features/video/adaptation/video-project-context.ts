import type { components } from "@inkforge/api-client";

import { browserApi } from "@/lib/api/browser";
import { requireApiData } from "@/lib/api/response";
import type { VideoAsset, VideoProject, VisualCanon } from "./types";
export { selectSeriesProject } from "./visual-canon-state";

export type VideoProjectContext = components["schemas"]["VideoProjectListResponse"];

export async function loadVideoProjectContext(novelId: string): Promise<VideoProjectContext> {
  return requireApiData(await browserApi.GET("/api/v1/video/novels/{novel_id}/projects", {
    params: { path: { novel_id: novelId } },
  }));
}

export async function createSeriesProject(novelId: string, title: string): Promise<VideoProject> {
  return requireApiData(await browserApi.POST("/api/v1/video/novels/{novel_id}/projects", {
    params: { path: { novel_id: novelId } },
    body: { title, mode: "series", targetAspectRatio: "9:16", targetLanguage: "zh-CN" },
  }));
}

export async function loadVisualCanons(projectId: string): Promise<VisualCanon[]> {
  return requireApiData(await browserApi.GET("/api/v1/video/projects/{project_id}/visual-canons", {
    params: { path: { project_id: projectId } },
  })).canons;
}

export async function findUploadedVisualAsset(projectId: string, sha256: string, duty: VisualCanon["duty"]): Promise<VideoAsset | null> {
  const detail = requireApiData(await browserApi.GET("/api/v1/video/projects/{project_id}", {
    params: { path: { project_id: projectId } },
  }));
  return detail.assets.find((asset) => asset.sha256 === sha256 && asset.duty === duty && asset.modality === "image") ?? null;
}

const changes = new Set<{ projectId: string; listener: () => void }>();

export function publishVisualCanonChange(projectId: string): void {
  for (const entry of changes) if (entry.projectId === projectId) entry.listener();
}

export function subscribeVisualCanonChange(projectId: string, listener: () => void): () => void {
  const entry = { projectId, listener };
  changes.add(entry);
  return () => { changes.delete(entry); };
}
