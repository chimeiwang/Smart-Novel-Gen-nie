"use client";

import { storyboardReviewPresentation } from "./storyboard-review-presentation";
import { StoryboardPreview } from "./storyboard-preview";
import type { ScriptVersion, StoryboardCandidate } from "./types";

export function StoryboardCandidateReview({ candidates, scriptVersions, draftRevision, scriptVersionId, baseStoryboardVersionId, busy, enabled, onAdopt }: {
  candidates: StoryboardCandidate[];
  scriptVersions: ScriptVersion[];
  draftRevision: number;
  scriptVersionId: string | null;
  baseStoryboardVersionId: string | null;
  busy: boolean;
  enabled: boolean;
  onAdopt: (candidate: StoryboardCandidate) => void;
}) {
  return <section className="episode-candidates episode-storyboard-candidates" aria-label="AI 分镜候选">
    <h3>AI 分镜候选</h3>
    {!candidates.length ? <p className="muted">任务完成后在这里逐镜审阅。候选不会自动写入工作稿。</p> : candidates.map((candidate) => {
      const review = storyboardReviewPresentation(candidate);
      const exactBasis = candidate.expectedDraftRevision === draftRevision
        && candidate.scriptVersionId === scriptVersionId
        && candidate.baseStoryboardVersionId === baseStoryboardVersionId;
      return <details className="episode-candidate" key={candidate.artifactId} open={candidate.status === "awaiting_user"}>
        <summary>{candidate.title} · {candidate.status === "applied" ? "已采用到工作稿" : candidate.status === "awaiting_user" ? "待审阅" : candidate.status === "rejected" ? "已拒绝" : "审阅中"}</summary>
        {candidate.summary ? <p>{candidate.summary}</p> : null}
        <p className="muted">依据工作稿 r{candidate.expectedDraftRevision} · 正式剧本 {candidate.scriptVersionId}。采用后仍需单独确认正式分镜。</p>
        <section className={`notice ${review.requiresReview ? "notice-warning" : ""}`}><strong>{review.label}</strong>{review.summary ? <p>{review.summary}</p> : null}{review.requiredChanges.length ? <ul>{review.requiredChanges.map((change, index) => <li key={index}>{change}</li>)}</ul> : null}{review.findings.map((finding, index) => <p key={`${finding.code}:${finding.shotId ?? finding.scriptSceneId ?? index}`}>{finding.message}</p>)}{candidate.review?.decision === "pass" ? <p className="muted">AI 审阅通过，仍由作者决定是否采用和确认。</p> : null}</section>
        <StoryboardPreview document={candidate.document} scriptVersion={scriptVersions.find((version) => version.id === candidate.scriptVersionId) ?? null} />
        {!exactBasis && candidate.status === "awaiting_user" ? <p className="notice notice-warning">工作稿或版本依据已经变化。此候选保持只读，请基于当前稿重新发起任务。</p> : null}
        <button className="button primary" type="button" disabled={!enabled || busy || candidate.status !== "awaiting_user" || !exactBasis} onClick={() => onAdopt(candidate)}>采用到分镜工作稿</button>
      </details>;
    })}
  </section>;
}
