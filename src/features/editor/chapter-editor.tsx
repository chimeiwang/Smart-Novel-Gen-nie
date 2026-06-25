"use client";

import { useEffect, useMemo, useRef, useState, useTransition } from "react";

import {
  generateContinuationAction,
  saveChapterDraftAction,
  setChapterStatusAction,
  updateChapterProgressAction,
} from "@/app/actions";
import { countTextLength } from "@/shared/lib/word-count";

type ChapterEditorProps = {
  novelId: string;
  chapter: {
    id: string;
    title: string;
    content: string;
    status: string;
    completedAt: string | null;
  };
  chapterProgress: string | null;
  styleName?: string | null;
};

export function ChapterEditor({
  novelId,
  chapter,
  chapterProgress,
  styleName,
}: ChapterEditorProps) {
  const [title, setTitle] = useState(chapter.title);
  const [content, setContent] = useState(chapter.content);
  const [saveStatus, setSaveStatus] = useState("已同步");
  const [length, setLength] = useState<"short" | "medium" | "long">("medium");
  const [isGenerating, startGenerating] = useTransition();
  const [chapterStatus, setChapterStatus] = useState(chapter.status);
  const [, startStatusTransition] = useTransition();

  // 章节进展状态
  const [progressContent, setProgressContent] = useState(chapterProgress ?? "");
  const [showProgress, setShowProgress] = useState(false);
  const [pendingProgress, startProgressTransition] = useTransition();

  const lastSavedRef = useRef({
    title: chapter.title,
    content: chapter.content,
  });

  useEffect(() => {
    if (
      title === lastSavedRef.current.title &&
      content === lastSavedRef.current.content
    ) {
      return;
    }

    const timer = window.setTimeout(async () => {
      setSaveStatus("保存中...");
      await saveChapterDraftAction({
        chapterId: chapter.id,
        title,
        content,
      });

      lastSavedRef.current = { title, content };
      setSaveStatus("已自动保存");
    }, 1200);

    return () => window.clearTimeout(timer);
  }, [chapter.id, content, title]);

  const chapterWordCount = useMemo(() => countTextLength(content), [content]);

  const handleGenerate = () => {
    startGenerating(async () => {
      setSaveStatus("AI 续写中...");
      const generated = await generateContinuationAction({
        novelId,
        chapterId: chapter.id,
        length,
      });

      if (generated) {
        setContent((current) => `${current.trimEnd()}\n\n${generated.trim()}`);
      }

      setSaveStatus("AI 续写完成，等待自动保存");
    });
  };

  const handleSaveProgress = () => {
    startProgressTransition(async () => {
      await updateChapterProgressAction({
        chapterId: chapter.id,
        content: progressContent,
      });
    });
  };

  const handleStatusChange = (status: "drafting" | "review" | "completed") => {
    startStatusTransition(async () => {
      await setChapterStatusAction({
        chapterId: chapter.id,
        status,
      });
      setChapterStatus(status);
    });
  };

  return (
    <div className="panel panel-flex">
      <div className="panel-header">
        <div className="meta">
          <span className="badge">当前章节 {chapterWordCount} 字</span>
          <span className={`status-text ${saveStatus.includes("已") ? "success" : ""}`}>
            {saveStatus}
          </span>
          <span className="badge">{getChapterStatusLabel(chapterStatus)}</span>
          {styleName ? <span className="badge">文风：{styleName}</span> : null}
        </div>
        <div className="row editor-actions">
          <select
            className="select"
            value={length}
            onChange={(event) =>
              setLength(event.target.value as "short" | "medium" | "long")
            }
          >
            <option value="short">短续写</option>
            <option value="medium">中续写</option>
            <option value="long">长续写</option>
          </select>
          <button className="button sm editor-ai-button" type="button" onClick={handleGenerate}>
            {isGenerating ? "生成中..." : "AI 续写"}
          </button>
        </div>
      </div>

      <div className="panel-body stack editor-layout">
        <input
          className="input"
          placeholder="章节标题"
          value={title}
          onChange={(event) => {
            setTitle(event.target.value);
            setSaveStatus("等待保存...");
          }}
        />

        <textarea
          className="textarea editor-area"
          placeholder="正文内容"
          value={content}
          onChange={(event) => {
            setContent(event.target.value);
            setSaveStatus("等待保存...");
          }}
        />

        {/* 章节进展 */}
        {showProgress ? (
          <div className="stack editor-progress">
            <textarea
              className="textarea textarea-resize"
              placeholder="记录本章节的进展、关键事件、伏笔等..."
              value={progressContent}
              onChange={(e) => setProgressContent(e.target.value)}
            />
            <div className="row row-end">
              <button
                className="button secondary sm"
                type="button"
                onClick={handleSaveProgress}
                disabled={pendingProgress}
              >
                {pendingProgress ? "保存中..." : "保存进展"}
              </button>
            </div>
          </div>
        ) : null}

      </div>

      <div className="panel-footer">
        <div className="row row-between">
          <button
            className="button ghost sm"
            type="button"
            onClick={() => setShowProgress(!showProgress)}
          >
            {showProgress ? "隐藏章节进展" : "章节进展"}
          </button>
          <div className="row">
            {chapterStatus !== "drafting" ? (
              <button
                className="button ghost sm"
                type="button"
                onClick={() => handleStatusChange("drafting")}
              >
                退回草稿
              </button>
            ) : null}
            {chapterStatus !== "review" ? (
              <button
                className="button secondary sm"
                type="button"
                onClick={() => handleStatusChange("review")}
              >
                送审
              </button>
            ) : null}
            {chapterStatus !== "completed" ? (
              <button
                className="button sm"
                type="button"
                onClick={() => handleStatusChange("completed")}
              >
                标记完成
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

function getChapterStatusLabel(status: string) {
  if (status === "review") return "待审";
  if (status === "completed") return "已完成";
  return "草稿";
}
