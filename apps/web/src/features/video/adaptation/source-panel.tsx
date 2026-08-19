"use client";

import { useRef } from "react";

import { countTextLength } from "@/shared/lib/word-count";
import { buildSourceSegmentsFromShots } from "./adaptation-state";
import type { SourceSelection } from "./types";

export function SourcePanel({
  sourceText,
  shots,
  selectedShotKey,
  editable,
  selection,
  onSelectShot,
  onSelection,
  onRewrite,
  onBind,
  onAddFromSelection,
  onClearSelection,
}: {
  sourceText: string;
  shots: Array<{ shotKey: string; sourceRanges: Array<{ start: number; end: number; sourceText: string }> }>;
  selectedShotKey: string | null;
  editable: boolean;
  selection: SourceSelection | null;
  onSelectShot: (shotKey: string) => void;
  onSelection: (selection: SourceSelection) => void;
  onRewrite: () => void;
  onBind: () => void;
  onAddFromSelection: () => void;
  onClearSelection: () => void;
}) {
  const copyRef = useRef<HTMLDivElement | null>(null);
  const segments = buildSourceSegmentsFromShots(sourceText, shots);

  const captureSelection = () => {
    if (!editable) return;
    const root = copyRef.current;
    const browserSelection = window.getSelection();
    if (!root || !browserSelection || browserSelection.rangeCount !== 1 || browserSelection.isCollapsed) return;
    const range = browserSelection.getRangeAt(0);
    if (!root.contains(range.commonAncestorContainer)) return;
    const before = document.createRange();
    before.selectNodeContents(root);
    before.setEnd(range.startContainer, range.startOffset);
    const prefix = before.toString();
    const selectedText = range.toString();
    if (!selectedText.trim()) return;
    const start = Array.from(prefix).length;
    onSelection({
      start,
      end: start + Array.from(selectedText).length,
      sourceText: selectedText,
      utf16Start: prefix.length,
      utf16End: prefix.length + selectedText.length,
    });
  };

  return (
    <section className="adaptation-source-panel">
      <header>
        <div><strong>章节原文</strong><span>原文只负责溯源，不决定切镜</span></div>
      </header>
      <div className="adaptation-source-copy" ref={copyRef} onMouseUp={captureSelection}>
        {segments.map((segment) => (
          <span
            key={`${segment.start}:${segment.end}`}
            className={`adaptation-source-segment ${segment.shotKeys.length ? "covered" : "omitted"} ${selectedShotKey && segment.shotKeys.includes(selectedShotKey) ? "selected" : ""}`}
            data-shot-label={segment.shotKeys.join(" · ")}
            onClick={() => segment.shotKeys[0] && onSelectShot(segment.shotKeys[0])}
          >
            {segment.text}
          </span>
        ))}
      </div>
      {selection ? (
        <div className="adaptation-source-selection">
          <span>已选 {countTextLength(selection.sourceText)} 字</span>
          <button className="button ghost sm" type="button" onClick={onRewrite}>让 AI 修改原文</button>
          <button className="button secondary sm" type="button" onClick={onAddFromSelection}>作为新镜头</button>
          <button className="button primary sm" type="button" onClick={onBind}>绑定当前镜头</button>
          <button className="button ghost sm" type="button" onClick={onClearSelection}>取消</button>
        </div>
      ) : null}
    </section>
  );
}
