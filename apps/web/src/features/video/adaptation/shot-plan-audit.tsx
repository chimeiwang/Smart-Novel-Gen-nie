"use client";

import type { ReviewFinding } from "./types";

export function ShotPlanAudit({
  reviewSummary,
  initialFindings,
  liveFindings,
  edited,
  onSelectShot,
}: {
  reviewSummary: string | null;
  initialFindings: ReviewFinding[];
  liveFindings: ReviewFinding[];
  edited: boolean;
  onSelectShot: (shotKey: string) => void;
}) {
  const liveIdentities = new Set(liveFindings.map(findingIdentity));
  const distinctInitialFindings = initialFindings.filter(
    (finding) => !liveIdentities.has(findingIdentity(finding)),
  );
  const correctedBindingCount = initialFindings.filter(
    (finding) => finding.message.startsWith("模型") && finding.message.includes("绑定已按所属节拍纠正"),
  ).length;
  return (
    <section className="adaptation-audit" aria-label="审镜建议">
      <header>
        <div><strong>审镜建议</strong><span>只提示风险，不替你决定拍法</span></div>
        {edited ? <em>AI 初审基于原始候选；目标覆盖已按当前编辑实时重算</em> : null}
      </header>
      {reviewSummary ? <p>{reviewSummary}</p> : null}
      {correctedBindingCount >= 5 ? (
        <div className="adaptation-audit-recommendation" role="status">
          <strong>建议重新生成这份候选</strong>
          <span>检测到 {correctedBindingCount} 处模型来源或目标归属纠正。你仍可逐镜编辑和确认，但重新生成通常比手工清理更可靠。</span>
        </div>
      ) : null}
      <FindingList
        title="当前目标覆盖"
        findings={liveFindings}
        defaultOpen={liveFindings.length <= 8}
        onSelectShot={onSelectShot}
      />
      <FindingList title="AI 初审证据" findings={distinctInitialFindings} onSelectShot={onSelectShot} />
      {!liveFindings.length && !distinctInitialFindings.length ? <div className="empty">当前没有待处理建议，仍建议逐镜确认画面职责。</div> : null}
    </section>
  );
}

function FindingList({
  title,
  findings,
  defaultOpen = false,
  onSelectShot,
}: {
  title: string;
  findings: ReviewFinding[];
  defaultOpen?: boolean;
  onSelectShot: (shotKey: string) => void;
}) {
  if (!findings.length) return null;
  const warningCount = findings.filter((finding) => finding.severity === "warning").length;
  return (
    <details className="adaptation-audit-group" open={defaultOpen || undefined}>
      <summary><strong>{title} · {findings.length}</strong>{warningCount ? <span>{warningCount} 项需注意</span> : null}</summary>
      <div>{findings.map((finding, index) => {
        const content = <>
          <span>{finding.severity === "warning" ? "需注意" : "可复核"}</span>
          <div><strong>{finding.scopeKey ? `${finding.scopeKey} · ` : ""}{finding.message}</strong><p>{finding.evidence}</p><small>{finding.suggestion}</small></div>
        </>;
        return finding.scope === "shot" && finding.scopeKey ? (
          <button type="button" key={`${finding.scope}:${finding.scopeKey}:${index}`} onClick={() => onSelectShot(finding.scopeKey ?? "")}>{content}</button>
        ) : (
          <article key={`${finding.scope}:${finding.scopeKey ?? "plan"}:${index}`}>{content}</article>
        );
      })}</div>
    </details>
  );
}

function findingIdentity(finding: ReviewFinding): string {
  return `${finding.scope}:${finding.scopeKey ?? "plan"}:${finding.message}:${finding.evidence}`;
}
