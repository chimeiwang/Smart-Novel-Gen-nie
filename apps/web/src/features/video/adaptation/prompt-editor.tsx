"use client";
/* eslint-disable @next/next/no-img-element */

import { countTextLength } from "@/shared/lib/word-count";
import { flattenFormalShots, groupFormalEpisodes } from "./adaptation-state";
import { formatDuration, shotScaleLabel } from "./shot-timeline";
import type { FormalPlan, FormalShot, PromptCandidate, PromptVersion, ShotVisualReference } from "./types";
import { assetPreviewUrl, dutyLabel, sameVisualReferences } from "./visual-canon-state";

export function PromptEditor({
  plan,
  selectedShot,
  candidate,
  candidates,
  versions,
  breakAfterShotIds,
  promptText,
  aspectRatio,
  visualReferences,
  currentVisualReferences,
  taskActive,
  working,
  onSelect,
  onPromptChange,
  onGenerate,
  onSave,
}: {
  plan: FormalPlan;
  selectedShot: FormalShot | null;
  candidate: PromptCandidate | null;
  candidates: PromptCandidate[];
  versions: PromptVersion[];
  breakAfterShotIds: string[];
  promptText: string;
  aspectRatio: string;
  visualReferences: ShotVisualReference[];
  currentVisualReferences: ShotVisualReference[];
  taskActive: boolean;
  working: string | null;
  onSelect: (shotKey: string) => void;
  onPromptChange: (value: string) => void;
  onGenerate: () => void;
  onSave: () => void;
}) {
  const shots = flattenFormalShots(plan);
  const navigationEpisodes = buildPromptNavigation(plan, breakAfterShotIds);
  const selectedVersion = versions.find((item) => item.shotId === selectedShot?.id) ?? null;
  const hasFrozenReferenceSnapshot = Boolean(candidate || selectedVersion);
  const referenceSnapshotChanged = hasFrozenReferenceSnapshot && !sameVisualReferences(
    visualReferences,
    currentVisualReferences,
  );
  const referenceSnapshotOwner = candidate ? "当前 AI 候选" : "当前正式版本";
  const referenceSnapshotMoment = candidate ? "生成时" : "保存时";
  return (
    <div className="adaptation-prompt-layout">
      <aside className="adaptation-prompt-shots">
        <header><strong>正式镜头</strong><span>{shots.length} 镜</span></header>
        <div>{navigationEpisodes.map((episode, episodeIndex) => (
          <section className="adaptation-prompt-episode" key={`episode-${episodeIndex + 1}`}>
            <h4>第 {episodeIndex + 1} 集 <span>{episode.shotCount} 镜</span></h4>
            {episode.scenes.map((scene) => (
              <section className="adaptation-prompt-scene" key={`${episodeIndex}:${scene.sceneKey}`}>
                <h5>{scene.sceneKey} · {scene.title}</h5>
                {scene.beats.map((beat) => (
                  <div className="adaptation-prompt-beat" key={`${episodeIndex}:${beat.beatKey}`}>
                    <small>{beat.beatKey} · {beat.title}</small>
                    {beat.shots.map((shot) => {
                      const saved = versions.find((item) => item.shotId === shot.id) ?? null;
                      const pendingCandidate = candidates.some((item) => item.shotId === shot.id);
                      return (
                        <button className={selectedShot?.id === shot.id ? "selected" : ""} type="button" key={shot.id} onClick={() => onSelect(shot.shotKey)}>
                          <span>{shot.shotKey}</span>
                          <span><strong>{shot.title}</strong><small>{pendingCandidate ? "AI 候选待确认" : saved ? saved.promptEdited ? "手动修改版" : "已保存" : "待生成"} · {formatDuration(shot.timelineDurationMs)}</small></span>
                        </button>
                      );
                    })}
                  </div>
                ))}
              </section>
            ))}
          </section>
        ))}</div>
      </aside>
      <section className="adaptation-prompt-main">
        {selectedShot ? (
          <>
            <header>
              <div><h3>{selectedShot.shotKey} · {selectedShot.title}</h3><span>{shotScaleLabel(selectedShot.shotScale)} · {formatDuration(selectedShot.timelineDurationMs)} · {aspectRatio}</span></div>
              <span className="badge">{candidate ? "AI 新候选" : selectedVersion ? selectedVersion.promptEdited ? "手动修改版" : "已保存" : "待生成"}</span>
            </header>
            <div className="adaptation-prompt-context">
              <div><strong>可见动作</strong><p>{selectedShot.visualIntent}</p></div>
              <div><strong>切镜理由</strong><p>{selectedShot.cutReason}</p></div>
              <div><strong>来源</strong><p>{selectedShot.sourceRanges.map((range) => range.sourceText).join(" / ") || "补充镜头，无独立原句"}</p></div>
            </div>
            {visualReferences.length ? (
              <section className="adaptation-prompt-references" aria-label="随提示词提交的视觉参考">
                <header><strong>本版本绑定 {visualReferences.length} 张参考图</strong><span>生成视频时需连同提示词一起提交</span></header>
                <div>{visualReferences.map((reference) => (
                  <figure key={reference.canonVersionId}>
                    <img src={assetPreviewUrl(reference.assetId)} alt={`${reference.settingName}${dutyLabel(reference.duty)}`} />
                    <figcaption><b>{reference.settingName}</b><span>{dutyLabel(reference.duty)} · {reference.label}</span><small>强度 {reference.strength}</small></figcaption>
                  </figure>
                ))}</div>
              </section>
            ) : (
              <div className="notice notice-warning">
                {referenceSnapshotChanged
                  ? `${referenceSnapshotOwner}${referenceSnapshotMoment}未绑定视觉参考，历史快照不会自动采用后来新增的图片。`
                  : "当前提示词没有绑定视觉参考，角色身份、服装和场景稳定性仍主要依赖文字。"}
              </div>
            )}
            {referenceSnapshotChanged ? (
              <section className="adaptation-reference-change notice notice-warning">
                <div>
                  <strong>当前镜头参考已更新</strong>
                  <span>
                    {referenceSnapshotOwner}固定 {visualReferences.length} 张，当前镜头为 {currentVisualReferences.length} 张；
                    重新生成候选后才会冻结当前版本与强度。
                  </span>
                </div>
                <button
                  className="button secondary sm"
                  type="button"
                  disabled={taskActive || working !== null}
                  onClick={onGenerate}
                >
                  {taskActive ? "生成中..." : "按当前参考重新生成"}
                </button>
              </section>
            ) : null}
            {candidate?.qualityWarnings?.length ? (
              <aside className="adaptation-prompt-warnings" aria-label="AI 候选质量提醒">
                <strong>AI 候选仍有 {candidate.qualityWarnings.length} 项需确认</strong>
                <ul>{candidate.qualityWarnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
              </aside>
            ) : null}
            {candidate ? (
              <details className="adaptation-prompt-spec">
                <summary>查看 AI 结构化提示词依据</summary>
                <dl>
                  <dt>主体与场景</dt><dd>{candidate.spec.subjectAndScene}</dd>
                  <dt>动作</dt><dd>{candidate.spec.visibleAction}</dd>
                  {candidate.spec.performance ? <><dt>表演</dt><dd>{candidate.spec.performance}</dd></> : null}
                  {candidate.spec.expressionAndGaze ? <><dt>表情与视线</dt><dd>{candidate.spec.expressionAndGaze}</dd></> : null}
                  <dt>摄影机</dt><dd>{candidate.spec.camera}</dd>
                  <dt>声音</dt><dd>{candidate.spec.audio}</dd>
                  {candidate.spec.continuity ? <><dt>连续性</dt><dd>{candidate.spec.continuity}</dd></> : null}
                </dl>
              </details>
            ) : null}
            <label className="video-field">即梦 2.5 提示词
              <textarea className="textarea adaptation-prompt-textarea" value={promptText} onChange={(event) => onPromptChange(event.target.value)} placeholder="AI 生成候选，或直接手动填写。" />
            </label>
            <footer>
              <button className="button primary" type="button" disabled={taskActive || working !== null} onClick={onGenerate}>{taskActive ? "生成中..." : candidate || selectedVersion ? "重新生成候选" : "AI 生成当前镜头"}</button>
              <button className="button secondary" type="button" disabled={!promptText.trim() || working !== null} onClick={onSave}>{working === "save-prompt" ? "保存中..." : "保存正式版本"}</button>
              <span>{countTextLength(promptText)} 字</span>
            </footer>
          </>
        ) : <div className="empty">请选择一个正式镜头。</div>}
      </section>
    </div>
  );
}

type PromptNavigationEpisode = {
  shotCount: number;
  scenes: Array<{
    sceneKey: string;
    title: string;
    beats: Array<{
      beatKey: string;
      title: string;
      shots: FormalShot[];
    }>;
  }>;
};

function buildPromptNavigation(
  plan: FormalPlan,
  breakAfterShotIds: string[],
): PromptNavigationEpisode[] {
  const context = new Map<string, { sceneKey: string; sceneTitle: string; beatKey: string; beatTitle: string }>();
  plan.scenes.forEach((scene) => scene.beats.forEach((beat) => beat.shots.forEach((shot) => {
    context.set(shot.id, {
      sceneKey: scene.sceneKey,
      sceneTitle: scene.title,
      beatKey: beat.beatKey,
      beatTitle: beat.title,
    });
  })));
  return groupFormalEpisodes(plan, breakAfterShotIds).map((episodeShots) => {
    const scenes: PromptNavigationEpisode["scenes"] = [];
    episodeShots.forEach((shot) => {
      const shotContext = context.get(shot.id);
      if (!shotContext) return;
      let scene = scenes.at(-1);
      if (!scene || scene.sceneKey !== shotContext.sceneKey) {
        scene = { sceneKey: shotContext.sceneKey, title: shotContext.sceneTitle, beats: [] };
        scenes.push(scene);
      }
      let beat = scene.beats.at(-1);
      if (!beat || beat.beatKey !== shotContext.beatKey) {
        beat = { beatKey: shotContext.beatKey, title: shotContext.beatTitle, shots: [] };
        scene.beats.push(beat);
      }
      beat.shots.push(shot);
    });
    return { shotCount: episodeShots.length, scenes };
  });
}
