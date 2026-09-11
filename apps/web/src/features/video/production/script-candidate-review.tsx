"use client";

import type { ScriptCandidate } from "./types";
import { scriptReviewPresentation } from "./script-review-presentation";

function CandidateReviewConclusion({ candidate }: { candidate: ScriptCandidate }) {
  const review = scriptReviewPresentation(candidate);
  return <section className={`notice ${review.requiresReview ? "notice-warning" : ""}`} aria-label="AI 审阅结论">
    <strong>{review.label}</strong>
    {review.summary ? <p>{review.summary}</p> : null}
    {review.requiredChanges.length ? <><h4>需要核对和修改</h4><ul>{review.requiredChanges.map((change, index) => <li key={index}>{change}</li>)}</ul></> : null}
    {review.findings.map((finding, index) => <p key={index}>{finding.message}</p>)}
    {candidate.review?.decision === "pass" ? <p className="muted">AI 审阅通过，仍由你决定是否采用和确认正式剧本。</p> : null}
  </section>;
}

export function ScriptCandidateReview({ candidates, draftRevision, busy, enabled, onAdopt }: { candidates: ScriptCandidate[]; draftRevision: number; busy: boolean; enabled: boolean; onAdopt: (candidate: ScriptCandidate) => void }) {
  return <section className="episode-candidates" aria-label="AI 剧本候选"><h3>AI 候选</h3>{!candidates.length ? <p className="muted">AI 完成后在这里审阅。候选不会自动写入剧本。</p> : candidates.map((candidate) => <details className="episode-candidate" key={candidate.artifactId} open={candidate.status === "awaiting_user"}><summary>{candidate.title} · {candidate.status === "applied" ? "已采用到工作稿" : candidate.status === "awaiting_user" ? "待审阅" : candidate.status === "rejected" ? "已拒绝" : "审阅中"}</summary><p>{candidate.summary}</p><p className="muted">依据工作稿 r{candidate.expectedDraftRevision}。采用后仍需单独确认正式剧本。</p><CandidateReviewConclusion candidate={candidate} />{(candidate.document.scenes ?? []).map((scene, index) => <article key={scene.id ?? scene.tempKey ?? index}><strong>第 {index + 1} 场 · {scene.title}</strong><p className="muted">{scene.locationLabel} · {scene.timeLabel} · {scene.narrativeTime}</p>{(scene.lines ?? []).map((line, lineIndex) => <p key={line.id ?? line.tempKey ?? lineIndex}>{line.kind === "dialogue" ? "对白：" : line.kind === "narration" ? "旁白：" : ""}{line.text}</p>)}</article>)}{candidate.status === "awaiting_user" && candidate.expectedDraftRevision !== draftRevision ? <p className="notice">工作稿已继续修改。此候选依据 r{candidate.expectedDraftRevision}，请重新发起修订，避免覆盖当前稿。</p> : null}<button className="button primary" type="button" disabled={!enabled || busy || candidate.status !== "awaiting_user" || candidate.expectedDraftRevision !== draftRevision} onClick={() => onAdopt(candidate)}>采用到工作稿</button></details>)}</section>;
}
