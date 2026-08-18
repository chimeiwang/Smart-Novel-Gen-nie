import { BeatTimeline, StageHeading, StageMissing } from "./video-stage-shared";
import { textFromRecord } from "./video-workspace-helpers";
import { readVideoPlanBeats, readVideoPlanTechnicalBase } from "./video-workspace-state";
import type { VideoStageCanvasProps } from "./video-workspace-types";

export function DirectionStage(props: VideoStageCanvasProps) {
  if (!props.scene?.plan) {
    return (
      <StageMissing
        message="请先批准场景地基候选。"
        action="前往场景地基"
        onClick={() => props.onChangeStage("foundation")}
      />
    );
  }
  const beats = readVideoPlanBeats(props.scene.plan);
  const technicalBase = readVideoPlanTechnicalBase(props.scene.plan);

  return (
    <section className="video-stage-content">
      <StageHeading
        eyebrow="任务 4"
        title="检查导演方案"
        description="时间轴必须从 0 秒连续覆盖目标时长；每个镜头节拍只使用一种主运镜。"
      />
      <div className="video-direction-summary">
        <div>
          <span>戏剧弧</span>
          <p>{textFromRecord(props.scene.plan, "dramaticArc") || "1.2 兼容方案未提供结构化戏剧弧"}</p>
        </div>
        <div>
          <span>视觉风格</span>
          <p>{textFromRecord(props.scene.plan, "visualStyle")}</p>
        </div>
        <div>
          <span>全片导演约束</span>
          <p>{textFromRecord(props.scene.plan, "globalDirection")}</p>
        </div>
        <div>
          <span>摄影基线</span>
          <p>{technicalBase.cinematography || "旧方案未提供结构化摄影基线"}</p>
        </div>
        <div>
          <span>灯光基线</span>
          <p>{technicalBase.lighting || "旧方案未提供结构化灯光基线"}</p>
        </div>
      </div>
      <BeatTimeline beats={beats} />
      <div className="video-stage-actions">
        <span className="status-text">导演方案会按稳定 slotId 引用素材，不重复创建人物或地点需求。</span>
        <button
          className="button primary"
          type="button"
          onClick={props.onCompilePreview}
          disabled={props.working === "prompt-preview"}
        >
          {props.working === "prompt-preview" ? "编译中..." : "编译提示词预览"}
        </button>
      </div>
    </section>
  );
}
