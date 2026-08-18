import { StageHeading } from "./video-stage-shared";
import type { VideoStageCanvasProps } from "./video-workspace-types";
import { countTextLength } from "@/shared/lib/word-count";

export function SourceStage(props: VideoStageCanvasProps) {
  const sourceCharacterCount = countTextLength(props.sourceText);
  const sourceCodePointCount = Array.from(props.sourceText).length;
  // 800 字以上提示用户收敛事件，2000 字以上则与服务端硬上限一致地禁止提交。
  const sourceClass = sourceCodePointCount > 2000
    ? "text-danger"
    : sourceCharacterCount > 800
      ? "text-warning"
      : "";
  const chapterContent = props.currentChapter?.content ?? "";

  return (
    <section className="video-stage-content">
      <StageHeading
        eyebrow="任务 1"
        title="冻结一个可制作的原文事件"
        description="建议选择 100～800 字、只包含一个可见事件的片段；服务端硬上限为 2000 字。"
      />
      {!props.currentChapter ? <div className="notice notice-danger">当前长篇没有可用章节。</div> : null}
      <div className="video-form-grid">
        <label className="video-field">
          <span>场景名称</span>
          <input
            className="input"
            value={props.sceneTitle}
            onChange={(event) => props.onSceneTitleChange(event.target.value)}
          />
        </label>
        <label className="video-field">
          <span>时长</span>
          <select
            className="select"
            value={props.durationSeconds}
            onChange={(event) => props.onDurationChange(Number(event.target.value))}
          >
            {[4, 6, 8, 10, 12, 15].map((value) => (
              <option value={value} key={value}>{value} 秒</option>
            ))}
          </select>
        </label>
      </div>
      <label className="video-field video-source-field">
        <span>当前章节原文 · 请直接拖选一个完整事件</span>
        <textarea
          className="textarea"
          value={chapterContent}
          placeholder="当前章节暂无正文。"
          readOnly
          onSelect={(event) => {
            const start = event.currentTarget.selectionStart;
            const end = event.currentTarget.selectionEnd;
            props.onSourceSelectionChange(start, end, chapterContent.slice(start, end));
          }}
        />
      </label>
      <label className="video-field video-source-field">
        <span className={sourceClass}>已选原文片段 · {sourceCharacterCount}/2000 字</span>
        <textarea
          className="textarea"
          value={props.sourceText}
          placeholder="请在上方章节正文中拖选原文。"
          readOnly
        />
      </label>
      <div className="video-stage-actions">
        <span className="status-text">来源会以全文哈希和长篇设定 fingerprint 冻结到本次任务。</span>
        <button
          className="button primary"
          type="button"
          disabled={
            !props.currentChapter
            || !props.sourceText.trim()
            || props.selectionStartUtf16 === null
            || props.selectionEndUtf16 === null
            || sourceCodePointCount > 2000
            || props.working === "scene"
          }
          onClick={props.onCreateScene}
        >
          {props.working === "scene" ? "正在生成..." : "冻结并生成场景地基"}
        </button>
      </div>
    </section>
  );
}
