import {
  formatVideoAssetBytes,
  isCompatiblePreviewAsset,
  videoAssetDutyLabel,
} from "./video-workspace-helpers";
import type { VideoPlanAssetView } from "./video-workspace-state";
import {
  VIDEO_ASSET_DUTIES,
  type AssetDuty,
  type AssetModality,
  type VideoAsset,
  type VideoAssetForm,
} from "./video-workspace-types";

export function AssetSlotGroup({
  title,
  description,
  slots,
  assets,
  selections,
  onSelect,
}: {
  title: string;
  description: string;
  slots: VideoPlanAssetView[];
  assets: VideoAsset[];
  selections: Record<string, string>;
  onSelect: (slotId: string, assetId: string) => void;
}) {
  return (
    <div className="video-slot-group">
      <div>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
      {slots.length === 0 ? <div className="empty">本场没有此类素材需求。</div> : null}
      <div className="video-slot-list">
        {slots.map((slot) => {
          // 只展示模态、职责和权利状态全部符合的素材，避免生成包绑定错误文件。
          const compatible = assets.filter((asset) => isCompatiblePreviewAsset(asset, slot));
          return (
            <article className="video-slot-card" key={slot.slotId}>
              <div className="video-slot-card-main">
                <div>
                  <span className="badge">{videoAssetDutyLabel(slot.duty as AssetDuty)}</span>
                  <h4>{slot.targetEntity}</h4>
                </div>
                <span className={`badge ${selections[slot.slotId] ? "badge-success" : "badge-warning"}`}>
                  {selections[slot.slotId] ? "本次已选择" : "待选择"}
                </span>
              </div>
              <p>采用：{slot.includeFeatures.join("、") || "未声明"}</p>
              {slot.excludeFeatures.length ? <p>排除：{slot.excludeFeatures.join("、")}</p> : null}
              <select
                className="select"
                value={selections[slot.slotId] ?? ""}
                onChange={(event) => onSelect(slot.slotId, event.target.value)}
              >
                <option value="">使用提示词占位</option>
                {compatible.map((asset) => (
                  <option key={asset.id} value={asset.id}>{asset.name}</option>
                ))}
              </select>
              {compatible.length === 0 ? (
                <span className="status-text">没有模态、职责和权利状态都匹配的素材。</span>
              ) : null}
            </article>
          );
        })}
      </div>
    </div>
  );
}

export function AssetLibrary({
  assets,
  form,
  working,
  onNameChange,
  onModalityChange,
  onDutyChange,
  onFileChange,
  onUpload,
  onConfirm,
}: {
  assets: VideoAsset[];
  form: VideoAssetForm;
  working: string | null;
  onNameChange: (value: string) => void;
  onModalityChange: (value: AssetModality) => void;
  onDutyChange: (value: AssetDuty) => void;
  onFileChange: (value: File | null) => void;
  onUpload: () => void;
  onConfirm: (assetId: string) => void;
}) {
  return (
    <details className="video-asset-library">
      <summary>素材库与上传器（{assets.length}）</summary>
      <div className="video-asset-upload-grid">
        <input
          className="input"
          placeholder="素材名称"
          value={form.assetName}
          onChange={(event) => onNameChange(event.target.value)}
        />
        <select
          className="select"
          value={form.assetModality}
          onChange={(event) => onModalityChange(event.target.value as AssetModality)}
        >
          <option value="image">图片</option>
          <option value="video">视频</option>
          <option value="audio">音频</option>
        </select>
        <select
          className="select"
          value={form.assetDuty}
          onChange={(event) => onDutyChange(event.target.value as AssetDuty)}
        >
          {VIDEO_ASSET_DUTIES.map((duty) => (
            <option key={duty.value} value={duty.value}>{duty.label}</option>
          ))}
        </select>
        <input
          className="input"
          type="file"
          onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
        />
        <button
          className="button secondary"
          type="button"
          disabled={!form.assetFile || !form.assetName.trim() || working === "asset-upload"}
          onClick={onUpload}
        >
          {working === "asset-upload" ? "上传中..." : "上传素材"}
        </button>
      </div>
      <div className="video-assets-list">
        {assets.map((asset) => (
          <div className="video-asset-row" key={asset.id}>
            <div>
              <strong>{asset.name}</strong>
              <span>
                {videoAssetDutyLabel(asset.duty)} · {asset.modality} · {formatVideoAssetBytes(asset.byteSize)}
              </span>
            </div>
            {asset.lockedAt ? <span className="badge badge-success">权利已确认</span> : (
              <button
                className="button secondary"
                type="button"
                disabled={working === `asset:${asset.id}`}
                onClick={() => onConfirm(asset.id)}
              >
                确认权利
              </button>
            )}
          </div>
        ))}
      </div>
    </details>
  );
}
