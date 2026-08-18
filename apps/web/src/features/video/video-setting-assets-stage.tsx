import { AssetLibrary, AssetSlotGroup } from "./video-assets";
import { StageHeading, StageMissing } from "./video-stage-shared";
import type { VideoStageCanvasProps } from "./video-workspace-types";

export function SettingAssetsStage(props: VideoStageCanvasProps) {
  if (!props.scene?.plan) {
    return (
      <StageMissing
        message="请先批准场景地基候选。"
        action="前往场景地基"
        onClick={() => props.onChangeStage("foundation")}
      />
    );
  }

  return (
    <section className="video-stage-content">
      <StageHeading
        eyebrow="任务 3"
        title="在设定槽位中选择素材"
        description="人物、关系、地点和道具素材直接显示在设定槽位卡中；动作、运镜等只进入场次专用引用。当前选择只用于本次提示词预览。"
      />
      <AssetSlotGroup
        title="长篇视频设定槽位"
        description="槽位来源锁定到本次任务中的 Character、CharacterRelation、Location、Item 或 WorldSetting。"
        slots={props.canonSlots}
        assets={props.assets}
        selections={props.previewSelections}
        onSelect={props.onSelectAsset}
      />
      <AssetSlotGroup
        title="场次专用引用"
        description="动作、运镜、环境声等不会污染项目人物和地点设定。"
        slots={props.sceneReferences}
        assets={props.assets}
        selections={props.previewSelections}
        onSelect={props.onSelectAsset}
      />
      <AssetLibrary
        assets={props.assets}
        form={props.assetForm}
        working={props.working}
        onNameChange={props.onAssetNameChange}
        onModalityChange={props.onAssetModalityChange}
        onDutyChange={props.onAssetDutyChange}
        onFileChange={props.onAssetFileChange}
        onUpload={props.onUploadAsset}
        onConfirm={props.onConfirmAsset}
      />
      <div className="video-stage-actions">
        <span className="status-text">刷新后需要重新选择；正式跨场景绑定等待目标 schema 上线。</span>
        <button
          className="button primary"
          type="button"
          onClick={() => props.onChangeStage("direction")}
        >
          查看导演方案
        </button>
      </div>
    </section>
  );
}
