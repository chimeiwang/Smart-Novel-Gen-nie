"use client";
/* eslint-disable @next/next/no-img-element */

import { useMemo, useState } from "react";

import { assetPreviewUrl, dutyLabel } from "../adaptation/visual-canon-state";
import type { VisualCanon } from "../adaptation/types";
import {
  PRODUCTION_KEYFRAME_ROLES,
  productionCapabilityProblems,
  productionKeyframeInputs,
  productionKeyframeProblems,
  type ProductionKeyframeSelection,
} from "./production-baseline-state";
import { TakeAdoptionReview } from "./take-adoption-review";
import type {
  CreateTakeAdoptionRequest,
  ProductionBaseline,
  ProductionCapability,
  ProductionKeyframeRole,
  ScriptVersion,
  StoryboardVersion,
  TakeAdoption,
  TakeCandidate,
} from "./types";

type KeyframeOption = {
  assetId: string;
  canonVersionId: string;
  label: string;
  current: boolean;
  previewUrl: string;
};

const ROLE_LABELS: Record<ProductionKeyframeRole, string> = {
  initial_state: "首帧",
  transition_anchor: "转折帧",
  end_state: "尾帧",
};

function approvedKeyframeOptions(canons: VisualCanon[]): KeyframeOption[] {
  const options = canons.flatMap((canon) => canon.versions
    .filter((version) => version.asset.modality === "image" && version.asset.rightsStatus === "confirmed" && version.asset.lockedAt !== null)
    .map((version) => ({
      assetId: version.asset.id,
      canonVersionId: version.id,
      label: `${canon.settingName} · ${version.label} · ${dutyLabel(canon.duty)} · v${version.versionNo}`,
      current: version.id === canon.currentVersionId,
      previewUrl: assetPreviewUrl(version.asset.id),
    })));
  options.sort((left, right) => Number(right.current) - Number(left.current) || left.label.localeCompare(right.label, "zh-CN"));
  return options.filter((option, index) => options.findIndex((item) => item.assetId === option.assetId) === index);
}

export function ProductionBaselineReview({ episodeId, storyboard, scriptVersion, currentBaseline, capability, canons, busy, enabled, selectedAdoptionIds, selectedKeyframes, onCreateAdoption, onSelectAdoption, onSelectKeyframe, onConfirm }: {
  episodeId: string;
  storyboard: StoryboardVersion;
  scriptVersion: ScriptVersion | null;
  currentBaseline: ProductionBaseline | null;
  capability: ProductionCapability;
  canons: VisualCanon[];
  busy: boolean;
  enabled: boolean;
  selectedAdoptionIds: Readonly<Record<string, string>>;
  selectedKeyframes: ProductionKeyframeSelection;
  onCreateAdoption: (candidate: TakeCandidate, comparison: CreateTakeAdoptionRequest["comparison"]) => Promise<TakeAdoption>;
  onSelectAdoption: (shotVersionId: string, adoptionId: string | null) => void;
  onSelectKeyframe: (shotVersionId: string, role: ProductionKeyframeRole, assetId: string | null) => void;
  onConfirm: () => void;
}) {
  const [acknowledgedFingerprint, setAcknowledgedFingerprint] = useState<string | null>(null);
  const keyframeOptions = useMemo(() => approvedKeyframeOptions(canons), [canons]);
  const availableAssetIds = useMemo(() => new Set(keyframeOptions.map((option) => option.assetId)), [keyframeOptions]);
  const capabilityProblems = productionCapabilityProblems(storyboard, capability);
  const keyframeProblems = productionKeyframeProblems(storyboard, selectedKeyframes, availableAssetIds, capability.maxImageReferences);
  const needsAcknowledgement = Boolean(currentBaseline);
  const adoptionCount = storyboard.shots.filter((shot) => Boolean(selectedAdoptionIds[shot.id])).length;
  const keyframeInputs = productionKeyframeInputs(storyboard, selectedKeyframes);
  const selectionFingerprint = [
    ...storyboard.shots.map((shot) => `${shot.id}:${selectedAdoptionIds[shot.id] ?? "pending"}`),
    ...keyframeInputs.map((keyframe) => `${keyframe.shotVersionId}:${keyframe.role}:${keyframe.assetId}`),
  ].join("|");
  const acknowledged = acknowledgedFingerprint === selectionFingerprint;

  return <div className="episode-baseline-review">
    <h3>确认新的制作基线</h3>
    <p>将正式剧本 v{scriptVersion?.versionNo ?? "?"} 与正式分镜 v{storyboard.versionNo} 冻结为一份不可变制作输入。当前制作和旧成片仍保留。</p>
    <div className="episode-baseline-combination"><span>剧本<strong>v{scriptVersion?.versionNo ?? "?"}</strong></span><span>分镜<strong>v{storyboard.versionNo}</strong></span><span>镜头<strong>{storyboard.shotCount}</strong></span><span>素材采用<strong>{adoptionCount}</strong></span><span>关键帧<strong>{keyframeInputs.length}</strong></span></div>
    <section className="notice"><strong>{adoptionCount ? `${adoptionCount} 镜会绑定已核对素材` : "本次全部镜头先进入待生产"}</strong><p>未选镜头保持待生产；生成成功不会自动成为采用，也不会改写原 Take 的生成清单。</p></section>
    <TakeAdoptionReview episodeId={episodeId} storyboard={storyboard} currentBaseline={currentBaseline} selectedAdoptionIds={selectedAdoptionIds} enabled={enabled} busy={busy} onCreateAdoption={onCreateAdoption} onSelectAdoption={onSelectAdoption} />
    <section className="episode-keyframe-review">
      <header><div><h4>逐镜关键帧</h4><p>从已批准的设定定妆版本中明确选择首帧、转折帧或尾帧。创建基线后将冻结素材哈希和定妆版本。</p></div><span>{keyframeInputs.length} 帧已选</span></header>
      {!keyframeOptions.length ? <p className="notice">当前没有可用的已批准定妆图片。可以先不选关键帧，或到设定中完成定妆确认后再回来。</p> : null}
      <div className="episode-keyframe-shot-list">{storyboard.shots.map((shot, index) => <article key={shot.id}>
        <header><div><span>镜头 {index + 1}</span><strong>{shot.content.title}</strong></div><small>{shot.content.productionIntent.references.length} 个视觉参考</small></header>
        <div className="episode-keyframe-role-grid">{PRODUCTION_KEYFRAME_ROLES.map((role) => {
          const selectedAssetId = selectedKeyframes[shot.id]?.[role] ?? "";
          const selectedOption = keyframeOptions.find((option) => option.assetId === selectedAssetId);
          return <label key={role}><span>{ROLE_LABELS[role]}</span><select className="select" value={selectedAssetId} disabled={!enabled || busy} onChange={(event) => onSelectKeyframe(shot.id, role, event.target.value || null)}><option value="">不设置</option>{selectedAssetId && !selectedOption ? <option value={selectedAssetId}>原选择已不可用</option> : null}{keyframeOptions.map((option) => <option value={option.assetId} key={`${role}:${option.canonVersionId}`}>{option.current ? "当前 · " : "历史 · "}{option.label}</option>)}</select>{selectedOption ? <span className="episode-keyframe-preview"><img src={selectedOption.previewUrl} alt={`${ROLE_LABELS[role]}：${selectedOption.label}`} /><small>{selectedOption.label}</small></span> : null}</label>;
        })}</div>
      </article>)}</div>
    </section>
    {capabilityProblems.length || keyframeProblems.length ? <section className="notice notice-danger"><strong>当前不能确认</strong><p>{[...capabilityProblems, ...keyframeProblems].join("；")}。请核对当前服务端能力、视觉参考和关键帧选择。</p></section> : null}
    {currentBaseline ? <label className="episode-baseline-ack"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledgedFingerprint(event.target.checked ? selectionFingerprint : null)} />我已核对：制作 v{currentBaseline.versionNo} 继续保留；新基线只带入上方明确选择的 {adoptionCount} 条采用记录和 {keyframeInputs.length} 个关键帧。</label> : null}
    <div className="episode-inline-actions"><button className="button primary" type="button" disabled={busy || capabilityProblems.length > 0 || keyframeProblems.length > 0 || (needsAcknowledgement && !acknowledged)} onClick={onConfirm}>{busy ? "正在确认…" : "确认并创建制作基线"}</button></div>
  </div>;
}
