import { VIDEO_STAGES, type VideoPlanAssetView, type VideoStage } from "./video-workspace-state";
import type {
  PromptPreview,
  VideoScene,
} from "./video-workspace-types";

type VideoReadinessInspectorProps = {
  previewEnabled: boolean;
  seedanceConfigured: boolean;
  scene: VideoScene | null;
  formalAssets: VideoPlanAssetView[];
  resolvedCount: number;
  missingCount: number;
  promptPreview: PromptPreview | null;
  onNextStage: (stage: VideoStage) => void;
};

export function VideoReadinessInspector({
  previewEnabled,
  seedanceConfigured,
  scene,
  formalAssets,
  resolvedCount,
  missingCount,
  promptPreview,
  onNextStage,
}: VideoReadinessInspectorProps) {
  const approved = Boolean(scene?.plan && scene.status === "approved");
  // 下一步由正式方案和当前预览产物推导，避免阶段按钮把未批准候选当成正式输入。
  const next: VideoStage = !scene
    ? "source"
    : !approved
      ? "foundation"
      : !promptPreview
        ? (formalAssets.length ? "settings" : "direction")
        : "package";
  const statuses = [
    { label: "来源", ok: Boolean(scene), value: scene ? "已冻结" : "未冻结" },
    { label: "地基", ok: approved, value: approved ? "已批准" : "待批准" },
    {
      label: "素材",
      ok: formalAssets.length === resolvedCount,
      value: `${resolvedCount}/${formalAssets.length}`,
    },
    { label: "方案", ok: approved, value: approved ? "正式预览版" : "无正式版" },
    { label: "提示词包", ok: Boolean(promptPreview), value: promptPreview ? "已编译" : "未编译" },
    { label: "真实渲染", ok: false, value: "固定关闭" },
  ];

  return (
    <aside className="panel video-readiness-panel">
      <div className="panel-header">
        <div>
          <h2 className="title-md">状态检查</h2>
          <span className="status-text">六轴预览状态</span>
        </div>
      </div>
      <div className="panel-body video-readiness-body">
        <div className="video-readiness-list">
          {statuses.map((status) => (
            <div key={status.label}>
              <span className={`status-dot ${status.ok ? "success" : "warning"}`} />
              <span>{status.label}</span>
              <strong>{status.value}</strong>
            </div>
          ))}
        </div>
        <div className="video-blockers">
          <h3>当前阻断</h3>
          {!previewEnabled ? <p>Core 开发预览开关未开启。</p> : null}
          {!scene ? <p>尚未冻结原文事件。</p> : null}
          {scene && !approved ? <p>场景地基候选尚未批准。</p> : null}
          {approved && missingCount > 0 ? <p>有 {missingCount} 个素材槽位使用占位引用。</p> : null}
          {promptPreview ? <p>该包是 preview_only，不能提交 Seedance。</p> : null}
        </div>
        <button className="button primary" type="button" onClick={() => onNextStage(next)}>
          {VIDEO_STAGES.find((item) => item.value === next)?.label ?? "继续"}
        </button>
        <div className="video-provider-state">
          <span>火山配置</span>
          <strong>{seedanceConfigured ? "已配置" : "未配置"}</strong>
          <p>不影响提示词包预览；真实调用仍由独立开关和正式制作包治理。</p>
        </div>
      </div>
    </aside>
  );
}
