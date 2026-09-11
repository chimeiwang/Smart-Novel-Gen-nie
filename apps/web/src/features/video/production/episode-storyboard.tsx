"use client";

import { useMemo, useState } from "react";

import { currentCanonVersion, dutyLabel } from "../adaptation/visual-canon-state";
import type { VisualCanon } from "../adaptation/types";
import {
  appendStoryboardShot,
  duplicateStoryboardShot,
  moveStoryboardShot,
  removeStoryboardShot,
  storyboardDurationMs,
  storyboardShotIdentity,
  updateStoryboardShot,
} from "./storyboard-document-state";
import type { ProductionCapability, ScriptScene, ScriptVersion, ShotReference, StoryboardDocument, StoryboardShot } from "./types";

type Props = {
  document: StoryboardDocument;
  scriptVersion: ScriptVersion | null;
  canons: VisualCanon[];
  capability: ProductionCapability;
  targetAspectRatio: StoryboardShot["productionIntent"]["ratio"];
  selectedShotId: string | null;
  disabled: boolean;
  onSelectedShotId: (identity: string | null) => void;
  onChange: (document: StoryboardDocument) => void;
};

type ReferenceChoice = {
  canonVersionId: string;
  label: string;
  strength: number;
};

const framingLabels: Record<StoryboardShot["framing"], string> = {
  extreme_wide: "大全景",
  wide: "全景",
  medium: "中景",
  close_up: "近景",
  detail: "特写",
  over_shoulder: "过肩",
  pov: "主观镜头",
};

const movementLabels: Record<StoryboardShot["cameraMovement"], string> = {
  static: "固定",
  pan: "横摇",
  tilt: "纵摇",
  dolly: "推拉",
  truck: "横移",
  crane: "升降",
  handheld: "手持",
  orbit: "环绕",
  zoom: "变焦",
};

export function EpisodeStoryboard({ document, scriptVersion, canons, capability, targetAspectRatio, selectedShotId, disabled, onSelectedShotId, onChange }: Props) {
  const scenes = useMemo(() => scriptVersion?.document.scenes ?? [], [scriptVersion]);
  const shots = useMemo(() => document.shots ?? [], [document]);
  const selectedShot = shots.find((shot) => storyboardShotIdentity(shot) === selectedShotId) ?? null;
  const referenceChoices = useMemo(() => canons.flatMap((canon): ReferenceChoice[] => {
    const version = currentCanonVersion(canon);
    return version ? [{ canonVersionId: version.id, label: `${version.settingName} · ${dutyLabel(canon.duty)} · ${version.label} v${version.versionNo}`, strength: version.defaultStrength }] : [];
  }), [canons]);
  const [newSceneId, setNewSceneId] = useState(scenes[0]?.id ?? "");
  const [newTitle, setNewTitle] = useState("");
  const [newAction, setNewAction] = useState("");
  const [newPrompt, setNewPrompt] = useState("");
  const [newReferenceIds, setNewReferenceIds] = useState<string[]>([]);
  const [feeConfirmed, setFeeConfirmed] = useState(false);
  const defaultDuration = capability.allowedDurationSeconds.includes(5) ? 5 : capability.allowedDurationSeconds[0];

  const effectiveNewSceneId = scenes.some((scene) => scene.id === newSceneId) ? newSceneId : scenes[0]?.id ?? "";

  const changeShot = (identity: string, patch: Partial<StoryboardShot>) => {
    onChange(updateStoryboardShot(document, identity, (shot) => ({ ...shot, ...patch })));
  };

  const addShot = () => {
    if (!defaultDuration || !effectiveNewSceneId || !newTitle.trim() || !newAction.trim() || !newPrompt.trim() || !newReferenceIds.length || (capability.feeConfirmationRequired && !feeConfirmed)) return;
    const references = newReferenceIds.flatMap((id): ShotReference[] => {
      const choice = referenceChoices.find((item) => item.canonVersionId === id);
      return choice ? [{ canonVersionId: id, strength: choice.strength }] : [];
    });
    const tempKey = crypto.randomUUID();
    const next = appendStoryboardShot(document, {
      tempKey,
      scriptSceneId: effectiveNewSceneId,
      title: newTitle.trim(),
      action: newAction.trim(),
      prompt: newPrompt.trim(),
      references,
      ratio: targetAspectRatio,
      capability,
      durationSeconds: defaultDuration,
      feeConfirmed,
    });
    onChange(next);
    onSelectedShotId(tempKey);
    setNewTitle("");
    setNewAction("");
    setNewPrompt("");
  };

  return <div className="episode-storyboard-grid">
    <section className="episode-storyboard-timeline">
      <header>
        <div><h3>正式剧本分镜</h3><p className="muted">{shots.length} 镜 · {(storyboardDurationMs(document) / 1000).toFixed(0)} 秒 · 镜头身份不随改名和排序变化</p></div>
      </header>
      {!scriptVersion ? <div className="episode-empty compact"><h4>先选择正式剧本</h4><p>分镜只能绑定本集已确认的剧本版本。</p></div> : null}
      {scriptVersion && scenes.map((scene, sceneIndex) => {
        if (!scene.id) return null;
        const sceneShots = shots.filter((shot) => shot.scriptSceneId === scene.id);
        return <section className="episode-storyboard-scene" key={scene.id}>
          <header><span>{String(sceneIndex + 1).padStart(2, "0")}</span><div><strong>{scene.title || "未命名场次"}</strong><small>{scene.locationLabel || "未设地点"} · {scene.timeLabel || "未设时间"}</small></div></header>
          <div className="episode-storyboard-shot-list">{sceneShots.map((shot, index) => {
            const identity = storyboardShotIdentity(shot);
            return <button type="button" className={identity === selectedShotId ? "selected" : ""} key={identity} onClick={() => onSelectedShotId(identity)}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <div><strong>{shot.title}</strong><small>{framingLabels[shot.framing]} · {movementLabels[shot.cameraMovement]} · {shot.durationMs / 1000}s</small></div>
              <em>{shot.id ? `稳定镜头 ${shot.id.slice(-6)}` : "身份待 Core 分配"}</em>
            </button>;
          })}</div>
          {!sceneShots.length ? <p className="muted">本场尚无镜头。</p> : null}
        </section>;
      })}
      {scriptVersion ? <details className="episode-add-shot" open={!shots.length || undefined}>
        <summary>新增镜头</summary>
        <div className="episode-add-shot-form">
          <label>所属场次<select className="select" disabled={disabled} value={effectiveNewSceneId} onChange={(event) => setNewSceneId(event.target.value)}>{scenes.flatMap((scene) => scene.id ? [<option key={scene.id} value={scene.id}>{scene.title || scene.id}</option>] : [])}</select></label>
          <label>镜头标题<input className="input" disabled={disabled} maxLength={240} value={newTitle} onChange={(event) => setNewTitle(event.target.value)} /></label>
          <label>可见动作<textarea className="textarea" disabled={disabled} maxLength={4000} rows={3} value={newAction} onChange={(event) => setNewAction(event.target.value)} /></label>
          <label>即梦 2.5 提示词<textarea className="textarea" disabled={disabled} maxLength={2500} rows={3} value={newPrompt} onChange={(event) => setNewPrompt(event.target.value)} /></label>
          <fieldset><legend>本镜冻结的视觉版本</legend>{referenceChoices.map((choice) => <label key={choice.canonVersionId}><input type="checkbox" disabled={disabled || (!newReferenceIds.includes(choice.canonVersionId) && newReferenceIds.length >= capability.maxImageReferences)} checked={newReferenceIds.includes(choice.canonVersionId)} onChange={(event) => setNewReferenceIds((current) => event.target.checked ? [...current, choice.canonVersionId] : current.filter((id) => id !== choice.canonVersionId))} />{choice.label}</label>)}</fieldset>
          {!referenceChoices.length ? <p className="notice notice-warning">项目中还没有可用的正式定妆版本。请到“创作资料”打开人物、地点或道具设定卡，在“视觉定妆”中确认至少一个版本，再创建可生产镜头。</p> : null}
          <p className="muted">服务端能力：{capability.provider} · {capability.model} · {capability.executionMode === "simulated" ? "隔离模拟" : "真实执行"} · {capability.allowedResolution} · {capability.allowedOutputFormat}</p>
          {capability.feeConfirmationRequired ? <label className="episode-fee-confirmation"><input type="checkbox" disabled={disabled} checked={feeConfirmed} onChange={(event) => setFeeConfirmed(event.target.checked)} />我确认此镜头按服务端真实执行配置可能产生供应商费用</label> : null}
          <button className="button" type="button" disabled={disabled || !defaultDuration || !effectiveNewSceneId || !newTitle.trim() || !newAction.trim() || !newPrompt.trim() || !newReferenceIds.length || (capability.feeConfirmationRequired && !feeConfirmed)} onClick={addShot}>添加到工作稿</button>
        </div>
      </details> : null}
    </section>
    <ShotInspector
      shot={selectedShot}
      scenes={scenes}
      referenceChoices={referenceChoices}
      capability={capability}
      disabled={disabled}
      onChange={changeShot}
      onMove={(identity, offset) => onChange(moveStoryboardShot(document, identity, offset))}
      onDuplicate={(shot) => {
        const identity = storyboardShotIdentity(shot);
        const tempKey = crypto.randomUUID();
        const next = duplicateStoryboardShot(document, identity, tempKey);
        if (next) { onChange(next); onSelectedShotId(tempKey); }
      }}
      onDelete={(shot) => {
        const identity = storyboardShotIdentity(shot);
        if (!window.confirm(`从当前工作稿移除“${shot.title}”？历史正式分镜不会改变。`)) return;
        onChange(removeStoryboardShot(document, identity));
      }}
    />
  </div>;
}

function ShotInspector({ shot, scenes, referenceChoices, capability, disabled, onChange, onMove, onDuplicate, onDelete }: {
  shot: StoryboardShot | null;
  scenes: ScriptScene[];
  referenceChoices: ReferenceChoice[];
  capability: ProductionCapability;
  disabled: boolean;
  onChange: (identity: string, patch: Partial<StoryboardShot>) => void;
  onMove: (identity: string, offset: -1 | 1) => void;
  onDuplicate: (shot: StoryboardShot) => void;
  onDelete: (shot: StoryboardShot) => void;
}) {
  if (!shot) return <aside className="episode-storyboard-inspector"><div className="empty">选择一个镜头，查看它绑定的剧本节点和制作输入。</div></aside>;
  const identity = storyboardShotIdentity(shot);
  const scene = scenes.find((item) => item.id === shot.scriptSceneId) ?? null;
  const lineIds = new Set(shot.scriptLineIds ?? []);
  const selectedReferences = shot.productionIntent.references;
  const availableDurations = [...new Set([shot.productionIntent.durationSeconds, ...capability.allowedDurationSeconds])].sort((left, right) => left - right);
  const capabilityMismatch = shot.productionIntent.provider !== capability.provider
    || shot.productionIntent.model !== capability.model
    || shot.productionIntent.generationMode !== capability.generationMode
    || shot.productionIntent.executionMode !== capability.executionMode
    || shot.productionIntent.resolution !== capability.allowedResolution
    || shot.productionIntent.outputFormat !== capability.allowedOutputFormat
    || !capability.allowedDurationSeconds.includes(shot.productionIntent.durationSeconds);
  const allReferences = [
    ...referenceChoices,
    ...selectedReferences.filter((reference) => !referenceChoices.some((choice) => choice.canonVersionId === reference.canonVersionId)).map((reference) => ({ canonVersionId: reference.canonVersionId, label: `历史视觉版本 ${reference.canonVersionId}`, strength: reference.strength ?? 70 })),
  ];
  const patchIntent = (patch: Partial<StoryboardShot["productionIntent"]>) => onChange(identity, { productionIntent: { ...shot.productionIntent, ...patch } });
  return <aside className="episode-storyboard-inspector">
    <header><div><span>{shot.id ? "稳定镜头" : "新镜头"}</span><strong>{shot.title}</strong></div><small>{shot.id ?? shot.tempKey}</small></header>
    <div className="episode-storyboard-inspector-scroll">
      <label>镜头标题<input className="input" disabled={disabled} maxLength={240} value={shot.title} onChange={(event) => onChange(identity, { title: event.target.value })} /></label>
      <label>所属剧本场次<select className="select" disabled={disabled} value={shot.scriptSceneId} onChange={(event) => onChange(identity, { scriptSceneId: event.target.value, scriptLineIds: [] })}>{scenes.flatMap((item) => item.id ? [<option key={item.id} value={item.id}>{item.title || item.id}</option>] : [])}</select></label>
      <fieldset><legend>确切台词／行动节点</legend>{(scene?.lines ?? []).flatMap((line) => line.id ? [<label key={line.id}><input type="checkbox" disabled={disabled} checked={lineIds.has(line.id)} onChange={(event) => onChange(identity, { scriptLineIds: event.target.checked ? [...lineIds, line.id!] : [...lineIds].filter((id) => id !== line.id) })} /><span>{line.kind === "dialogue" ? "对白" : line.kind === "narration" ? "旁白" : "行动"} · {line.text || "空内容"}</span></label>] : [])}{!(scene?.lines?.length) ? <p className="muted">本场没有可绑定的稳定台词节点。</p> : null}</fieldset>
      <label>可见动作<textarea className="textarea" disabled={disabled} maxLength={4000} rows={4} value={shot.action} onChange={(event) => onChange(identity, { action: event.target.value })} /></label>
      <div className="grid-two"><label>景别<select className="select" disabled={disabled} value={shot.framing} onChange={(event) => onChange(identity, { framing: event.target.value as StoryboardShot["framing"] })}>{Object.entries(framingLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>机位运动<select className="select" disabled={disabled} value={shot.cameraMovement} onChange={(event) => onChange(identity, { cameraMovement: event.target.value as StoryboardShot["cameraMovement"] })}>{Object.entries(movementLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div>
      <div className="grid-two"><label>片段时长<select className="select" disabled={disabled} value={shot.productionIntent.durationSeconds} onChange={(event) => { const seconds = Number(event.target.value); onChange(identity, { durationMs: seconds * 1000, productionIntent: { ...shot.productionIntent, durationSeconds: seconds } }); }}>{availableDurations.map((seconds) => <option key={seconds} value={seconds} disabled={!capability.allowedDurationSeconds.includes(seconds)}>{seconds} 秒{capability.allowedDurationSeconds.includes(seconds) ? "" : "（历史配置）"}</option>)}</select></label><label>画幅<select className="select" disabled={disabled} value={shot.productionIntent.ratio} onChange={(event) => patchIntent({ ratio: event.target.value as StoryboardShot["productionIntent"]["ratio"] })}>{["9:16", "16:9", "4:3", "1:1", "3:4", "21:9", "adaptive"].map((ratio) => <option key={ratio} value={ratio}>{ratio}</option>)}</select></label></div>
      <label>即梦 2.5 提示词<textarea className="textarea" disabled={disabled} maxLength={2500} rows={5} value={shot.productionIntent.prompt} onChange={(event) => patchIntent({ prompt: event.target.value })} /></label>
      <section className="episode-shot-provider"><strong>生成清单</strong><span>{shot.productionIntent.provider} · {shot.productionIntent.model}</span><span>参考图模式 · {shot.productionIntent.resolution} · {shot.productionIntent.outputFormat}</span><span className={`status ${shot.productionIntent.executionMode === "simulated" ? "warning" : "danger"}`}>{shot.productionIntent.executionMode === "simulated" ? "隔离模拟，不调用供应商、不产生费用" : "真实执行，可能产生供应商费用"}</span>{capabilityMismatch ? <div className="notice notice-warning"><p>这份工作稿使用的生成能力与服务端当前允许值不同。历史输入保持不变，明确选择后才会更新。</p>{capability.executionMode === "simulated" && selectedReferences.length <= capability.maxImageReferences && capability.allowedDurationSeconds.length ? <button className="button ghost sm" type="button" disabled={disabled} onClick={() => { const seconds = capability.allowedDurationSeconds.includes(shot.productionIntent.durationSeconds) ? shot.productionIntent.durationSeconds : capability.allowedDurationSeconds[0]!; onChange(identity, { durationMs: seconds * 1000, productionIntent: { ...shot.productionIntent, provider: capability.provider, model: capability.model, generationMode: capability.generationMode, executionMode: capability.executionMode, feeConfirmed: false, durationSeconds: seconds, resolution: capability.allowedResolution, outputFormat: capability.allowedOutputFormat } }); }}>改用服务端当前模拟能力</button> : <p>当前能力需要费用确认或现有参考超过上限，本轮不会自动改写。</p>}</div> : null}<label><input type="checkbox" disabled={disabled} checked={shot.productionIntent.generateAudio} onChange={(event) => patchIntent({ generateAudio: event.target.checked })} />生成原生声音</label><label><input type="checkbox" disabled={disabled} checked={shot.productionIntent.watermark} onChange={(event) => patchIntent({ watermark: event.target.checked })} />添加水印</label></section>
      <fieldset><legend>冻结视觉版本（至少 1 项）</legend>{allReferences.map((choice) => {
        const selected = selectedReferences.find((reference) => reference.canonVersionId === choice.canonVersionId);
        return <div className="episode-shot-reference" key={choice.canonVersionId}><label><input type="checkbox" disabled={disabled || Boolean(selected && selectedReferences.length === 1) || (!selected && selectedReferences.length >= capability.maxImageReferences)} checked={Boolean(selected)} onChange={(event) => patchIntent({ references: event.target.checked ? [...selectedReferences, { canonVersionId: choice.canonVersionId, strength: choice.strength }] : selectedReferences.filter((reference) => reference.canonVersionId !== choice.canonVersionId) })} /><span>{choice.label}</span></label>{selected ? <input aria-label={`${choice.label}参考强度`} type="range" min={1} max={100} disabled={disabled} value={selected.strength ?? choice.strength} onChange={(event) => patchIntent({ references: selectedReferences.map((reference) => reference.canonVersionId === choice.canonVersionId ? { ...reference, strength: Number(event.target.value) } : reference) })} /> : null}</div>;
      })}</fieldset>
      <div className="episode-storyboard-actions"><button className="button ghost" type="button" disabled={disabled} onClick={() => onMove(identity, -1)}>上移</button><button className="button ghost" type="button" disabled={disabled} onClick={() => onMove(identity, 1)}>下移</button><button className="button ghost" type="button" disabled={disabled || !shot.id} title={shot.id ? "复制会创建带明确沿袭关系的新镜头" : "等待 Core 分配稳定身份后才能复制"} onClick={() => onDuplicate(shot)}>复制为新镜头</button><button className="button ghost text-danger" type="button" disabled={disabled} onClick={() => onDelete(shot)}>从工作稿移除</button></div>
    </div>
  </aside>;
}
