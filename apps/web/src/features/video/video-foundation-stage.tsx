import { useState, type FormEvent } from "react";

import { createClientRequestId } from "@/lib/api/client-request-id";
import { PlanOverview, StageHeading, StageMissing } from "./video-stage-shared";
import {
  LEGACY_PROMPT_NOTICE,
  normalizeSeedancePromptPackage,
  textFromRecord,
} from "./video-workspace-helpers";
import {
  readVideoPlanAssets,
  readVideoPlanBeats,
  resolveVideoFoundationVersion,
} from "./video-workspace-state";
import type { VideoStageCanvasProps } from "./video-workspace-types";

const MAX_REVISION_MESSAGE_CHARACTERS = 2_000;

type CandidateRevisionFormProps = Pick<
  VideoStageCanvasProps,
  "working" | "onReviseScene"
> & {
  sceneId: string;
  artifactRevision: number;
};

type CandidateApprovalButtonProps = Pick<
  VideoStageCanvasProps,
  "working" | "onApproveScene"
> & {
  sceneId: string;
  artifactRevision: number;
};

function CandidateApprovalButton({
  sceneId,
  artifactRevision,
  working,
  onApproveScene,
}: CandidateApprovalButtonProps) {
  // 网络结果不确定时复用同一个请求标识；候选 revision 变化会由父级 key 重建。
  const [clientRequestId] = useState(() => createClientRequestId());
  const reviewDecisionWorking = working === `approve:${sceneId}`
    || working === `revise:${sceneId}`;
  return (
    <button
      className="button primary"
      type="button"
      disabled={reviewDecisionWorking}
      onClick={() => onApproveScene(sceneId, artifactRevision, clientRequestId)}
    >
      {working === `approve:${sceneId}` ? "批准中..." : "批准候选方案"}
    </button>
  );
}

function CandidateRevisionForm({
  sceneId,
  artifactRevision,
  working,
  onReviseScene,
}: CandidateRevisionFormProps) {
  const [userMessage, setUserMessage] = useState("");
  // 同一次表单提交失败后继续复用该键；Artifact revision 变化时父级 key 会重建表单与幂等键。
  const [clientRequestId] = useState(() => createClientRequestId());
  const reviewDecisionWorking = working === `approve:${sceneId}` || working === `revise:${sceneId}`;
  const normalizedMessage = userMessage.trim();
  const messageTooLong = normalizedMessage.length > MAX_REVISION_MESSAGE_CHARACTERS;

  const submitRevision = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!normalizedMessage || messageTooLong || reviewDecisionWorking) return;
    onReviseScene(sceneId, artifactRevision, normalizedMessage, clientRequestId);
  };

  return (
    <form className="stack" onSubmit={submitRevision}>
      <label className="stack">
        <span>返工意见（必填）</span>
        <textarea
          className="textarea"
          name="userMessage"
          required
          rows={4}
          disabled={reviewDecisionWorking}
          placeholder="请具体说明需要调整的镜头任务、表演调度、摄影、灯光或声音。"
          value={userMessage}
          onChange={(event) => setUserMessage(event.target.value)}
        />
      </label>
      {messageTooLong ? (
        <div className="notice notice-danger" role="alert">
          返工意见当前为 {normalizedMessage.length} 字，最多允许 {MAX_REVISION_MESSAGE_CHARACTERS} 字。
        </div>
      ) : null}
      <div className="row">
        <button
          className="button secondary"
          type="submit"
          disabled={reviewDecisionWorking || !normalizedMessage || messageTooLong}
        >
          {working === `revise:${sceneId}` ? "正在返工..." : "返工并重新生成"}
        </button>
        <span className="muted">返工会复用已冻结的原文与设定，不会新建重复场景。</span>
      </div>
    </form>
  );
}

export function FoundationStage(props: VideoStageCanvasProps) {
  const scene = props.scene;
  if (!scene) {
    return (
      <StageMissing
        message="请先冻结原文事件。"
        action="前往原文事件"
        onClick={() => props.onChangeStage("source")}
      />
    );
  }
  if (scene.status === "generating") {
    return <StageMissing message="DeepSeek 正在生成严格结构，请稍候。" />;
  }
  if (scene.status === "failed" && !scene.plan) {
    const retrying = props.working === `retry:${scene.id}`;
    return (
      <section className="video-stage-content">
        <StageHeading
          eyebrow="任务 2"
          title="场景规划生成失败"
          description="重试会逐字复用原任务的冻结原文与设定快照，不会新建场景。"
        />
        {scene.latestTask?.lastErrorMessage ? (
          <div className="notice notice-danger">{scene.latestTask.lastErrorMessage}</div>
        ) : null}
        <StageMissing
          message="修复规划器后，可以在同一场景上重新生成。"
          action={retrying ? "重新提交中..." : "重新生成当前场景"}
          disabled={retrying}
          onClick={() => props.onRetryScene(scene.id)}
        />
      </section>
    );
  }

  // 候选和正式方案分别解析，防止未批准候选混入后续素材与导演阶段。
  const candidateAssets = readVideoPlanAssets(scene.candidatePlan);
  const candidateBeats = readVideoPlanBeats(scene.candidatePlan);
  const formalBeats = readVideoPlanBeats(scene.plan);
  const candidatePrompt = scene.candidatePackage
    ? normalizeSeedancePromptPackage(scene.candidatePackage)
    : null;
  const foundationVersion = resolveVideoFoundationVersion(scene);
  const reviewDecisionWorking = props.working === `approve:${scene.id}`
    || props.working === `revise:${scene.id}`;

  return (
    <section className="video-stage-content">
      <StageHeading
        eyebrow="任务 2"
        title="审核场景地基候选"
        description="候选与正式版本分开展示；只有作者批准后，素材槽位和导演方案才成为本次预览的正式输入。"
      />
      {scene.latestTask?.lastErrorMessage ? (
        <div className="notice notice-danger">{scene.latestTask.lastErrorMessage}</div>
      ) : null}
      {foundationVersion === "candidate" && scene.candidatePlan && scene.reviewArtifact ? (
        <div className="video-version-panel candidate">
          <div className="video-version-heading">
            <div>
              <span className="badge badge-warning">待批准候选</span>
              <h3>{textFromRecord(scene.candidatePlan, "title") || scene.title}</h3>
            </div>
            <CandidateApprovalButton
              key={`${scene.reviewArtifact.id}:${scene.reviewArtifact.revision}`}
              sceneId={scene.id}
              artifactRevision={scene.reviewArtifact.revision}
              working={props.working}
              onApproveScene={props.onApproveScene}
            />
          </div>
          <p>{textFromRecord(scene.candidatePlan, "summary")}</p>
          <PlanOverview assets={candidateAssets} beats={candidateBeats} />
          {scene.candidatePackage && candidatePrompt ? (
            <div>
              <div className="video-package-summary">
                <span className="badge">
                  {candidatePrompt.isLegacy ? "旧版提示词包" : "Provider 提示词"}
                </span>
                <span className="badge">{candidatePrompt.providerPromptCharacterCount} 字</span>
                {candidatePrompt.providerLengthState === "warning" ? (
                  <span className="badge badge-warning">
                    超过 {scene.candidatePackage.recommendedPromptCharacters} 字建议值（非阻断）
                  </span>
                ) : null}
              </div>
              <pre className="video-prompt-preview">{candidatePrompt.providerPrompt}</pre>
              {candidatePrompt.isLegacy ? <div className="notice">{LEGACY_PROMPT_NOTICE}</div> : null}
              {candidatePrompt.providerLengthState === "blocked" ? (
                <div className="notice notice-danger">
                  Provider 提示词超过当前安全上限，当前包不能提交。
                </div>
              ) : null}
              {(scene.candidatePackage.warnings ?? []).map((warning) => (
                <div className="notice" key={warning}>{warning}</div>
              ))}
              {candidatePrompt.hasDistinctManifest ? (
                <details>
                  <summary>
                    完整制作清单 · {candidatePrompt.manifestPromptCharacterCount} 字
                  </summary>
                  <pre className="video-prompt-preview">{candidatePrompt.manifestPrompt}</pre>
                </details>
              ) : null}
            </div>
          ) : null}
          <CandidateRevisionForm
            key={`${scene.id}:${scene.reviewArtifact.id}:${scene.reviewArtifact.revision}`}
            sceneId={scene.id}
            artifactRevision={scene.reviewArtifact.revision}
            working={props.working}
            onReviseScene={props.onReviseScene}
          />
        </div>
      ) : null}
      {foundationVersion === "formal" && scene.plan ? (
        <div className="video-version-panel formal">
          <div className="video-version-heading">
            <div>
              <span className="badge badge-success">正式预览方案 v{scene.revision}</span>
              <h3>{textFromRecord(scene.plan, "title") || scene.title}</h3>
            </div>
            <button
              className="button secondary"
              type="button"
              onClick={() => props.onChangeStage("settings")}
            >
              准备设定素材
            </button>
          </div>
          <p>{textFromRecord(scene.plan, "summary")}</p>
          <PlanOverview assets={props.canonSlots} beats={formalBeats} />
        </div>
      ) : null}
      {foundationVersion === "none" ? (
        <StageMissing message="当前场景没有可审核的地基方案。" />
      ) : null}
    </section>
  );
}
