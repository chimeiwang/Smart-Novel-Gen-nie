import type { EpisodeDetail, ScriptVersion } from "./types";

export function episodeVersionLabels(detail: EpisodeDetail) {
  return { draft: `工作稿 r${detail.scriptDraft.revision}`, script: detail.currentScriptVersion ? `正式剧本 v${detail.currentScriptVersion.versionNo}` : "尚未确认正式剧本", production: detail.episode.currentProductionBaselineId ? `制作 ${detail.episode.currentProductionBaselineId}` : "尚无制作基线", delivery: detail.episode.latestDeliveryVersionId ? `交付 ${detail.episode.latestDeliveryVersionId}` : "尚无成片" };
}

export function EpisodeVersionContext({ detail, viewingVersion, onView }: { detail: EpisodeDetail; viewingVersion: ScriptVersion | null; onView: (version: ScriptVersion | null) => void }) {
  const labels = episodeVersionLabels(detail);
  return <section className="episode-version-context" aria-label="本集版本依据">
    <div className="episode-version-grid"><span>{labels.draft}</span><span>{labels.script}</span><span>{labels.production}</span><span>{labels.delivery}</span></div>
    <div className="episode-toolbar"><label>查看剧本<select className="select" value={viewingVersion?.id ?? "draft"} onChange={(event) => onView(detail.scriptVersions.find((version) => version.id === event.target.value) ?? null)}><option value="draft">当前工作稿（可编辑）</option>{detail.scriptVersions.map((version) => <option key={version.id} value={version.id}>正式剧本 v{version.versionNo} · 只读</option>)}</select></label><p className="muted">确认新版剧本不会替换已有制作与成片。</p></div>
  </section>;
}
