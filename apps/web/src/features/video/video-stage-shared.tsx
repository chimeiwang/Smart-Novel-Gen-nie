import type { VideoPlanAssetView, VideoPlanBeatView } from "./video-workspace-state";

export function StageHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <header className="video-stage-heading">
      <span>{eyebrow}</span>
      <h3>{title}</h3>
      <p>{description}</p>
    </header>
  );
}

export function StageMissing({
  message,
  action,
  onClick,
  disabled = false,
}: {
  message: string;
  action?: string;
  onClick?: () => void;
  disabled?: boolean;
}) {
  return (
    <div className="video-stage-empty">
      <p>{message}</p>
      {action && onClick ? (
        <button
          className="button primary"
          type="button"
          disabled={disabled}
          onClick={onClick}
        >
          {action}
        </button>
      ) : null}
    </div>
  );
}

export function PlanOverview({
  assets,
  beats,
}: {
  assets: VideoPlanAssetView[];
  beats: VideoPlanBeatView[];
}) {
  return (
    <div className="video-plan-overview">
      <div>
        <strong>{assets.length}</strong>
        <span>设定/参考槽位</span>
      </div>
      <div>
        <strong>{beats.length}</strong>
        <span>连续镜头节拍</span>
      </div>
    </div>
  );
}

export function BeatTimeline({ beats }: { beats: VideoPlanBeatView[] }) {
  return (
    <div className="video-timeline">
      {beats.map((beat) => (
        <div key={beat.beatId}>
          <strong>{beat.startSecond}–{beat.endSecond}s</strong>
          <span>{[beat.shotSize, beat.lens, beat.cameraMovement].filter(Boolean).join(" · ")}</span>
          <div className="video-beat-details">
            {beat.dramaticPurpose ? <p><b>镜头任务</b>{beat.dramaticPurpose}</p> : null}
            {beat.performanceDirection ? <p><b>表演指导</b>{beat.performanceDirection}</p> : null}
            {beat.blocking ? <p><b>场面调度</b>{beat.blocking}</p> : null}
            {beat.cameraMotivation ? <p><b>摄影动机</b>{beat.cameraMotivation}</p> : null}
            {beat.axisTransition ? <p><b>轴线</b>{beat.axisTransition}</p> : null}
            <p><b>机位</b>{beat.cameraPosition || "旧方案未提供结构化机位"}</p>
            <p><b>构图</b>{beat.composition || "旧方案未提供结构化构图"}</p>
            <p><b>焦点</b>{beat.focus || "旧方案未提供结构化焦点"}</p>
            <p><b>灯光</b>{beat.lighting || "旧方案未提供结构化灯光"}</p>
            <p><b>动作</b>{beat.action}</p>
            {beat.sound ? <p><b>声音</b>{beat.sound}</p> : null}
          </div>
        </div>
      ))}
    </div>
  );
}
