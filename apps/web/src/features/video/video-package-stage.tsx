import { StageHeading, StageMissing } from "./video-stage-shared";
import {
  LEGACY_PROMPT_NOTICE,
  normalizeSeedancePromptPackage,
  readSeedancePackageStatus,
  videoAssetDutyLabel,
} from "./video-workspace-helpers";
import type { VideoStageCanvasProps } from "./video-workspace-types";

export function PackageStage(props: VideoStageCanvasProps) {
  if (!props.scene?.plan) {
    return (
      <StageMissing
        message="请先批准场景方案。"
        action="前往场景地基"
        onClick={() => props.onChangeStage("foundation")}
      />
    );
  }
  const packageValue = props.promptPreview?.promptPackage;
  const promptPresentation = packageValue
    ? normalizeSeedancePromptPackage(packageValue)
    : null;
  const packageStatus = packageValue ? readSeedancePackageStatus(packageValue) : null;

  return (
    <section className="video-stage-content">
      <StageHeading
        eyebrow="任务 5"
        title="Seedance 提示词包"
        description="默认展示面向 Provider 的短提示词；完整制作清单可展开审阅。开发预览包不会调用火山供应商。"
      />
      {!packageValue || !promptPresentation || !packageStatus ? (
        <div className="video-stage-empty compact">
          <p>尚未按当前素材选择编译预览。</p>
          <button
            className="button primary"
            type="button"
            onClick={props.onCompilePreview}
            disabled={props.working === "prompt-preview"}
          >
            {props.working === "prompt-preview" ? "编译中..." : "生成提示词预览"}
          </button>
        </div>
      ) : (
        <>
          <div className="video-package-summary">
            <span className={`badge ${packageValue.previewOnly ? "badge-warning" : "badge-success"}`}>
              {packageStatus.previewLabel}
            </span>
            <span className={`badge ${packageValue.assetReady ? "badge-success" : "badge-warning"}`}>
              {packageStatus.assetLabel}
            </span>
            <span className={`badge ${packageValue.submissionReady ? "badge-success" : "badge-warning"}`}>
              {packageStatus.submissionLabel}
            </span>
            <span className="badge">
              {promptPresentation.isLegacy ? "旧版提示词包" : "Provider"}{" "}
              {promptPresentation.providerPromptCharacterCount}/{packageValue.maxPromptCharacters} 字
            </span>
            {promptPresentation.providerLengthState === "warning" ? (
              <span className="badge badge-warning">
                超过 {packageValue.recommendedPromptCharacters} 字建议值（非阻断）
              </span>
            ) : null}
            <span className="badge">{packageValue.output.durationSeconds} 秒</span>
            <span className="badge">{packageValue.output.ratio}</span>
            <span className="badge">{packageValue.output.resolution}</span>
          </div>
          <pre className="video-prompt-preview light">{promptPresentation.providerPrompt}</pre>
          {promptPresentation.isLegacy ? <div className="notice">{LEGACY_PROMPT_NOTICE}</div> : null}
          {promptPresentation.providerLengthState === "blocked" ? (
            <div className="notice notice-danger">
              Provider 提示词超过 {packageValue.maxPromptCharacters} 字安全上限，当前包不能提交。
            </div>
          ) : null}
          {(packageValue.warnings ?? []).map((warning) => (
            <div className="notice" key={warning}>{warning}</div>
          ))}
          {promptPresentation.hasDistinctManifest ? (
            <details>
              <summary>
                完整制作清单 · {promptPresentation.manifestPromptCharacterCount} 字
              </summary>
              <pre className="video-prompt-preview light">{promptPresentation.manifestPrompt}</pre>
            </details>
          ) : null}
          <div className="video-package-mapping">
            <h3>素材映射</h3>
            {packageValue.assetBindings.map((binding) => (
              <div key={binding.assetId}>
                <code>{binding.alias}</code>
                <span>{binding.targetEntity} · {videoAssetDutyLabel(binding.duty)}</span>
                <span className={`badge ${binding.isFixture ? "badge-warning" : "badge-success"}`}>
                  {binding.isFixture ? "待补素材" : "本次已解析"}
                </span>
              </div>
            ))}
          </div>
          {props.promptPreview?.missingSlotIds.length ? (
            <div className="notice">
              仍缺 {props.promptPreview.missingSlotIds.length} 个素材槽位；提示词保留完整占位说明。
            </div>
          ) : null}
          {packageStatus.blockers.map((blocker) => (
            <div className="notice" key={blocker}>{blocker}</div>
          ))}
          {packageStatus.readyMessage ? (
            <div className="notice">{packageStatus.readyMessage}</div>
          ) : null}
        </>
      )}
    </section>
  );
}
