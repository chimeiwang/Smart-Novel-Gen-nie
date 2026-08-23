import { DirectionStage } from "./video-direction-stage";
import { FoundationStage } from "./video-foundation-stage";
import { PackageStage } from "./video-package-stage";
import { SettingAssetsStage } from "./video-setting-assets-stage";
import { SourceStage } from "./video-source-stage";
import type { VideoStageCanvasProps } from "./video-workspace-types";

// 画布只做阶段路由；请求、轮询和 URL 同步始终留在工作台容器。
export function VideoStageCanvas(props: VideoStageCanvasProps) {
  if (props.stage === "source") return <SourceStage {...props} />;
  if (props.stage === "foundation") return <FoundationStage {...props} />;
  if (props.stage === "settings") return <SettingAssetsStage {...props} />;
  if (props.stage === "direction") return <DirectionStage {...props} />;
  return <PackageStage {...props} />;
}
