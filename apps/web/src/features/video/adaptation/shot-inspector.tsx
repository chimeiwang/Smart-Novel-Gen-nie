"use client";

import { formatDuration, shotScaleLabel, type TimelineShot } from "./shot-timeline";
import { purposeLabel } from "./adaptation-state";
import type { CandidateShot, CoverageGoal } from "./types";

export function ShotInspector({
  shot,
  sceneTitle,
  beatTitle,
  coverageGoals,
  editable,
  discardedCount,
  onChange,
  onMerge,
  onDelete,
  onRestore,
  onAdd,
  onToggleGoal,
}: {
  shot: TimelineShot | null;
  sceneTitle: string;
  beatTitle: string;
  coverageGoals: CoverageGoal[];
  editable: boolean;
  discardedCount: number;
  onChange: (patch: Partial<Omit<CandidateShot, "shotKey" | "sourceRanges">>) => void;
  onMerge: () => void;
  onDelete: () => void;
  onRestore: () => void;
  onAdd: (purpose: CandidateShot["narrativePurpose"]) => void;
  onToggleGoal: (goalKey: string) => void;
}) {
  if (!shot) {
    return <aside className="adaptation-inspector"><div className="empty">请选择一个镜头。</div></aside>;
  }
  return (
    <aside className="adaptation-inspector">
      <header>
        <div><span>{shot.shotKey}</span><strong>{shot.title}</strong></div>
        <small>{sceneTitle} · {beatTitle}</small>
      </header>
      <div className="adaptation-inspector-scroll">
        <div className="adaptation-inspector-summary">
          <span>{purposeLabel(shot.narrativePurpose)}</span>
          <span>{shotScaleLabel(shot.shotScale)}</span>
          <span>{formatDuration(shot.timelineDurationMs)}</span>
        </div>
        <label className="video-field">镜头标题
          <input className="input" disabled={!editable} value={shot.title} onChange={(event) => onChange({ title: event.target.value })} />
        </label>
        <label className="video-field">本镜作用
          <textarea className="textarea" disabled={!editable} value={shot.storyFunction} onChange={(event) => onChange({ storyFunction: event.target.value })} />
        </label>
        <label className="video-field">观众获得
          <textarea className="textarea" disabled={!editable} value={shot.audienceGain} onChange={(event) => onChange({ audienceGain: event.target.value })} />
        </label>
        <section className="adaptation-inspector-goals">
          <strong>本镜承担的叙事目标</strong>
          <div>{coverageGoals.map((goal) => (
            <label key={goal.goalKey}>
              <input
                type="checkbox"
                disabled={!editable}
                checked={(shot.coveredGoalKeys ?? []).includes(goal.goalKey)}
                onChange={() => onToggleGoal(goal.goalKey)}
              />
              <span>{goal.goalKey} · {goal.description}</span>
            </label>
          ))}</div>
        </section>
        <div className="grid-two">
          <label className="video-field">镜头目的
            <select className="select" disabled={!editable} value={shot.narrativePurpose} onChange={(event) => onChange({ narrativePurpose: event.target.value as CandidateShot["narrativePurpose"] })}>
              {PURPOSE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <label className="video-field">与原文关系
            <select className="select" disabled={!editable} value={shot.sourceRelation} onChange={(event) => onChange({ sourceRelation: event.target.value as CandidateShot["sourceRelation"] })}>
              <option value="direct">原文直呈</option>
              <option value="derived">合理推导</option>
              <option value="supplemental">视听补充</option>
            </select>
          </label>
        </div>
        <div className="grid-two">
          <label className="video-field">景别/构图
            <select className="select" disabled={!editable} value={shot.shotScale} onChange={(event) => onChange({ shotScale: event.target.value as CandidateShot["shotScale"] })}>
              {SHOT_SCALE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <label className="video-field">成片时长
            <input className="input" type="number" min={0.5} max={15} step={0.5} disabled={!editable} value={shot.timelineDurationMs / 1000} onChange={(event) => onChange({ timelineDurationMs: Math.round(Number(event.target.value) * 2) * 500 })} />
          </label>
        </div>
        <div className="grid-two">
          <label className="video-field">机位角度
            <select className="select" disabled={!editable} value={shot.cameraAngle} onChange={(event) => onChange({ cameraAngle: event.target.value as CandidateShot["cameraAngle"] })}>
              <option value="eye_level">平视</option><option value="high_angle">俯拍</option><option value="low_angle">仰拍</option><option value="overhead">顶拍</option><option value="dutch_angle">倾斜机位</option>
            </select>
          </label>
          <label className="video-field">摄影机运动
            <select className="select" disabled={!editable} value={shot.cameraMovement} onChange={(event) => onChange({ cameraMovement: event.target.value as CandidateShot["cameraMovement"] })}>
              {CAMERA_MOVEMENT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
        </div>
        <label className="video-field">可见动作与调度
          <textarea className="textarea" disabled={!editable} value={shot.visualIntent} onChange={(event) => onChange({ visualIntent: event.target.value })} />
        </label>
        <div className="grid-two">
          <label className="video-field">对白位置
            <select className="select" disabled={!editable} value={shot.speechMode} onChange={(event) => onChange({
              speechMode: event.target.value as CandidateShot["speechMode"],
              spokenText: event.target.value === "none" ? null : shot.spokenText ?? "请填写实际台词",
            })}>
              <option value="none">无对白</option><option value="sync">画内对白</option><option value="offscreen">画外对白</option><option value="voiceover">旁白</option>
            </select>
          </label>
          <label className="video-field">环境声与音效
            <input className="input" disabled={!editable} value={shot.soundDesign} onChange={(event) => onChange({ soundDesign: event.target.value })} />
          </label>
        </div>
        {shot.speechMode !== "none" ? <label className="video-field">实际台词
          <textarea className="textarea" disabled={!editable} value={shot.spokenText ?? ""} onChange={(event) => onChange({ spokenText: event.target.value })} />
        </label> : null}
        <label className="video-field">为什么在这里切镜
          <textarea className="textarea" disabled={!editable} value={shot.cutReason} onChange={(event) => onChange({ cutReason: event.target.value })} />
        </label>
        <section className="adaptation-inspector-source">
          <strong>原文来源</strong>
          <p>{shot.sourceRanges.map((range) => range.sourceText).join(" / ") || "补充镜头，无独立原句"}</p>
        </section>
        {editable ? (
          <>
            <section className="adaptation-add-shot">
              <strong>在当前镜头后新增</strong>
              <div>{PURPOSE_OPTIONS.filter((item) => ["establishing", "action", "reaction", "insert", "transition"].includes(item.value)).map((option) => (
                <button className="button ghost sm" type="button" key={option.value} onClick={() => onAdd(option.value)}>{option.label}</button>
              ))}</div>
            </section>
            <div className="adaptation-inspector-actions">
              <button className="button secondary sm" type="button" onClick={onMerge}>与下一镜合并</button>
              <button className="button ghost sm text-danger" type="button" onClick={onDelete}>删除镜头</button>
              {discardedCount ? <button className="button ghost sm" type="button" onClick={onRestore}>恢复最近删除</button> : null}
            </div>
          </>
        ) : null}
      </div>
    </aside>
  );
}

const PURPOSE_OPTIONS: Array<{ value: CandidateShot["narrativePurpose"]; label: string }> = [
  { value: "establishing", label: "建立" }, { value: "action", label: "动作" },
  { value: "dialogue", label: "对白" }, { value: "reaction", label: "反应" },
  { value: "reveal", label: "揭示" }, { value: "insert", label: "插入" },
  { value: "transition", label: "转场" }, { value: "atmosphere", label: "氛围" },
];

const SHOT_SCALE_OPTIONS: Array<{ value: CandidateShot["shotScale"]; label: string }> = [
  { value: "extreme_long", label: "大全景" }, { value: "long", label: "全景" },
  { value: "medium", label: "中景" }, { value: "medium_close", label: "中近景" },
  { value: "close", label: "近景" }, { value: "extreme_close", label: "特写" },
  { value: "over_shoulder", label: "过肩" }, { value: "two_shot", label: "双人镜头" },
  { value: "pov", label: "主观镜头" },
];

const CAMERA_MOVEMENT_OPTIONS: Array<{ value: CandidateShot["cameraMovement"]; label: string }> = [
  { value: "locked", label: "固定" }, { value: "pan", label: "横摇" },
  { value: "tilt", label: "纵摇" }, { value: "push_in", label: "推近" },
  { value: "pull_out", label: "拉远" }, { value: "tracking", label: "跟随" },
  { value: "arc", label: "环绕" }, { value: "handheld", label: "手持" },
  { value: "focus_shift", label: "焦点转移" },
];
