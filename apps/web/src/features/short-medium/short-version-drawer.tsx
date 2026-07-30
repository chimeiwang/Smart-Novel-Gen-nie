"use client";

import type { ConfirmedVersionAction } from "./short-workspace-state";

export type ShortVersionSummary = {
  id: string;
  versionNumber: number;
  status: "awaiting_user" | "applied";
  source: "agent" | "manual" | "restore";
  sourceOutlineVersionId?: string | null;
  createdAt: string;
};

export type ShortVersionDiffBlock = {
  type: "insert" | "delete" | "replace";
  oldStart: number;
  oldEnd: number;
  newStart: number;
  newEnd: number;
  oldText?: string | null;
  newText?: string | null;
};

export type ShortVersionDiff = {
  fromVersionId?: string | null;
  toVersionId?: string | null;
  fromWordCount: number;
  toWordCount: number;
  wordCountDelta: number;
  confirmationHash: string;
  blocks: ShortVersionDiffBlock[];
};

type ShortVersionDrawerProps = {
  open: boolean;
  title: string;
  versions: ShortVersionSummary[];
  diff: ShortVersionDiff | null;
  pendingAction: ConfirmedVersionAction | null;
  currentOutlineVersionId?: string | null;
  disabled?: boolean;
  onInspect: (versionId: string) => void;
  onConfirm: (action: ConfirmedVersionAction, confirmationHash: string) => void;
  onClose: () => void;
};

const SOURCE_LABELS: Record<ShortVersionSummary["source"], string> = {
  agent: "Agent 候选",
  manual: "人工提交",
  restore: "历史恢复",
};

export function ShortVersionDrawer({
  open,
  title,
  versions,
  diff,
  pendingAction,
  currentOutlineVersionId = null,
  disabled = false,
  onInspect,
  onConfirm,
  onClose,
}: ShortVersionDrawerProps) {
  if (!open) return null;

  return (
    <aside className="panel short-version-drawer" aria-label={`${title}版本`}>
      <header className="short-version-drawer-header">
        <div>
          <h2>{title}版本</h2>
          <p className="muted">候选不会自动采用；提交、采用和恢复都需要确认同一份完整差异。</p>
        </div>
        <button className="button ghost" type="button" onClick={onClose}>关闭</button>
      </header>

      <div className="short-version-list">
        {versions.map((version) => (
          <button
            className="short-version-item"
            type="button"
            key={version.id}
            onClick={() => onInspect(version.id)}
          >
            <strong>v{version.versionNumber}</strong>
            <span>{SOURCE_LABELS[version.source]}</span>
            <span>{version.status === "awaiting_user" ? "待采用" : "已应用"}</span>
            {version.sourceOutlineVersionId ? (
              <span title={version.sourceOutlineVersionId}>
                基于{version.sourceOutlineVersionId === currentOutlineVersionId
                  ? "当前蓝图"
                  : "旧蓝图"}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      {diff ? (
        <section className="short-version-diff" aria-label="完整版本差异">
          <header>
            <strong>
              {diff.fromVersionId ? "当前版本" : "空白基线"} →{" "}
              {diff.toVersionId ? "所选版本" : "当前工作稿"}
            </strong>
            <span>
              {diff.fromWordCount} 字 → {diff.toWordCount} 字（{diff.wordCountDelta >= 0 ? "+" : ""}
              {diff.wordCountDelta}）
            </span>
          </header>
          <div className="short-version-diff-content">
            {diff.blocks.length ? diff.blocks.map((block, index) => (
              <article className={`diff-block diff-${block.type}`} key={`${index}:${block.type}`}>
                {block.oldText != null ? (
                  <pre aria-label="删除内容">- {block.oldText}</pre>
                ) : null}
                {block.newText != null ? (
                  <pre aria-label="新增内容">+ {block.newText}</pre>
                ) : null}
              </article>
            )) : <p className="muted">没有文本差异。</p>}
          </div>
          {pendingAction ? (
            <button
              className="button"
              type="button"
              disabled={disabled}
              onClick={() => onConfirm(pendingAction, diff.confirmationHash)}
            >
              确认{pendingAction === "submit" ? "提交" : pendingAction === "adopt" ? "采用" : "恢复"}
            </button>
          ) : null}
        </section>
      ) : (
        <p className="muted">请选择一个版本或先预览当前工作稿。</p>
      )}
    </aside>
  );
}
