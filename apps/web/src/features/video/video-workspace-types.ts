import type { components } from "@inkforge/api-client";

import type { VideoPlanAssetView, VideoStage } from "./video-workspace-state";

// 视频工作台只消费生成客户端类型，避免前端再维护一套易漂移的业务 DTO。
export type VideoProject = components["schemas"]["VideoProjectResponse"];
export type VideoProjectList = components["schemas"]["VideoProjectListResponse"];
export type VideoProjectDetail = components["schemas"]["VideoProjectDetailResponse"];
export type VideoScene = components["schemas"]["VideoSceneResponse"];
export type VideoAsset = components["schemas"]["VideoAssetResponse"];
export type PromptPreview = components["schemas"]["PromptPreviewResponse"];
export type AssetModality = VideoAsset["modality"];
export type AssetDuty = VideoAsset["duty"];

export type VideoWorkspaceProps = {
  novelId: string;
  novelName: string;
  currentChapter?: {
    id: string;
    title: string;
    content: string;
    updatedAt: string;
  };
};

export type VideoAssetForm = {
  assetName: string;
  assetModality: AssetModality;
  assetDuty: AssetDuty;
  assetFile: File | null;
};

// 五阶段共享同一份受控状态和动作，阶段组件不得自行请求或改写服务端数据。
export type VideoStageCanvasProps = {
  stage: VideoStage;
  currentChapter?: VideoWorkspaceProps["currentChapter"];
  scene: VideoScene | null;
  sceneTitle: string;
  sourceText: string;
  selectionStartUtf16: number | null;
  selectionEndUtf16: number | null;
  durationSeconds: number;
  working: string | null;
  assets: VideoAsset[];
  canonSlots: VideoPlanAssetView[];
  sceneReferences: VideoPlanAssetView[];
  previewSelections: Record<string, string>;
  promptPreview: PromptPreview | null;
  assetForm: VideoAssetForm;
  onSceneTitleChange: (value: string) => void;
  onSourceSelectionChange: (start: number, end: number, value: string) => void;
  onDurationChange: (value: number) => void;
  onCreateScene: () => void;
  onRetryScene: (sceneId: string) => void;
  onApproveScene: (
    sceneId: string,
    expectedArtifactRevision: number,
    clientRequestId: string,
  ) => void;
  onReviseScene: (
    sceneId: string,
    expectedArtifactRevision: number,
    userMessage: string,
    clientRequestId: string,
  ) => void;
  onSelectAsset: (slotId: string, assetId: string) => void;
  onAssetNameChange: (value: string) => void;
  onAssetModalityChange: (value: AssetModality) => void;
  onAssetDutyChange: (value: AssetDuty) => void;
  onAssetFileChange: (value: File | null) => void;
  onUploadAsset: () => void;
  onConfirmAsset: (assetId: string) => void;
  onCompilePreview: () => void;
  onChangeStage: (stage: VideoStage) => void;
};

export const VIDEO_ASSET_DUTIES: ReadonlyArray<{ value: AssetDuty; label: string }> = [
  { value: "identity", label: "人物身份" },
  { value: "costume", label: "服装妆造" },
  { value: "scene", label: "地点空间" },
  { value: "prop", label: "关键道具" },
  { value: "style", label: "视觉风格" },
  { value: "storyboard", label: "故事板" },
  { value: "keyframe", label: "关系/关键帧" },
  { value: "motion", label: "动作参考" },
  { value: "camera", label: "运镜参考" },
  { value: "voice", label: "人物音色" },
  { value: "ambience", label: "环境声音" },
  { value: "music", label: "音乐参考" },
];
