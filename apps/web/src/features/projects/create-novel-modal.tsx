"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { browserApi } from "@/lib/api/browser";
import { requireApiData } from "@/lib/api/response";
import {
  isValidShortStoryTargetReference,
  parseOptionalShortStoryTarget,
  STORY_LENGTH_PROFILE_CONFIG,
  type StoryLengthProfile,
} from "@/shared/contracts/story-length-profile";

interface CreateNovelModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function CreateNovelModal({ isOpen, onClose }: CreateNovelModalProps) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [summary, setSummary] = useState("");
  const [inspiration, setInspiration] = useState("");
  const [storyLengthProfile, setStoryLengthProfile] = useState<StoryLengthProfile | null>(null);
  const [targetTotalWordCount, setTargetTotalWordCount] = useState("");
  const [genre, setGenre] = useState("");
  const [protagonist, setProtagonist] = useState("");
  const [coreSellingPoint, setCoreSellingPoint] = useState("");
  const [readerPromise, setReaderPromise] = useState("");
  const [firstChapterGoal, setFirstChapterGoal] = useState("");

  const handleSubmit = async (formData: FormData) => {
    if (!storyLengthProfile) return;
    setPending(true);
    setError(null);
    try {
      const shortTarget = parseOptionalShortStoryTarget(targetTotalWordCount);
      const longTarget = Number(targetTotalWordCount);
      const result = requireApiData(await browserApi.POST("/api/v1/novels", {
        body: storyLengthProfile === "short_medium"
          ? {
              storyLengthProfile: "short_medium",
              name: name.trim() || null,
              inspiration: inspiration.trim(),
              targetTotalWordCount: shortTarget,
            }
          : {
              storyLengthProfile: "long_serial",
              name: String(formData.get("name") ?? ""),
              summary: String(formData.get("summary") ?? "") || null,
              targetTotalWordCount: longTarget || null,
              genre: genre || null,
              protagonist: protagonist || null,
              coreSellingPoint: coreSellingPoint || null,
              readerPromise: readerPromise || null,
              firstChapterGoal: firstChapterGoal || null,
            },
      }));

      if (storyLengthProfile === "short_medium") {
        try {
          const session = requireApiData(await browserApi.POST("/api/v1/writing/sessions", {
            body: {
              novelId: result.novelId,
              chapterId: result.chapterId,
              title: "中短篇大纲",
            },
          }));
          requireApiData(await browserApi.POST("/api/v1/writing/runs", {
            body: {
              clientRequestId: crypto.randomUUID(),
              novelId: result.novelId,
              chapterId: result.chapterId,
              writingSessionId: session.id,
              workflowKind: "short_medium",
              operation: "develop_short_outline",
              targetWordCount: shortTarget,
              userMessage: "请根据创建时的灵感生成可供确认的完整中短篇大纲。",
            },
          }));
        } catch (error) {
          console.error("中短篇项目已创建，但大纲任务启动失败，可在工作区重试", error);
        }
      }

      onClose();
      router.push(`/workspace/${result.novelId}`);
      router.refresh();
    } catch (error) {
      setError(error instanceof Error ? error.message : "创建作品失败");
    } finally {
      setPending(false);
    }
  };

  const selectStoryLengthProfile = (profile: StoryLengthProfile) => {
    setStoryLengthProfile(profile);
    setTargetTotalWordCount(profile === "short_medium" ? "" : "1000000");
    setError(null);
  };

  const shortTarget = parseOptionalShortStoryTarget(targetTotalWordCount);
  const shortFormValid = inspiration.trim().length > 0
    && isValidShortStoryTargetReference(shortTarget);
  const canSubmit = storyLengthProfile === "short_medium"
    ? shortFormValid
    : storyLengthProfile === "long_serial" && name.trim().length > 0;

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="title-lg">开始一个新故事</h2>
          <button className="button ghost icon" type="button" onClick={onClose} title="关闭">
            ×
          </button>
        </div>
        <div className="modal-body">
          <form action={handleSubmit} className="stack">
            <p className="muted">先选择作品篇幅。中短篇从灵感和完整大纲开始，长篇保留章节连载流程。</p>
            <div className="stack">
              <span className="label">创作模式</span>
              <div className="story-profile-grid">
                {(["short_medium", "long_serial"] as const).map((profile) => {
                  const config = STORY_LENGTH_PROFILE_CONFIG[profile];
                  const active = storyLengthProfile === profile;
                  return (
                    <button
                      key={profile}
                      className={`story-profile-option ${active ? "active" : ""}`}
                      type="button"
                      aria-pressed={active}
                      onClick={() => selectStoryLengthProfile(profile)}
                    >
                      <span>{config.label}</span>
                      <small>{config.targetWords[0]}-{config.targetWords[1]} 字</small>
                    </button>
                  );
                })}
              </div>
            </div>

            {storyLengthProfile === "short_medium" ? (
              <>
                <label className="stack">
                  <span>暂定标题（可选）</span>
                  <input
                    className="input"
                    name="name"
                    placeholder="可以稍后再决定"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                  />
                </label>
                <label className="stack">
                  <span>灵感</span>
                  <textarea
                    className="textarea"
                    name="inspiration"
                    placeholder="可以是开头、结尾、设定，或几句话的大纲"
                    required
                    value={inspiration}
                    onChange={(event) => setInspiration(event.target.value)}
                  />
                </label>
                <label className="stack">
                  <span>篇幅参考（可选）</span>
                  <input
                    className="input"
                    name="targetTotalWordCount"
                    type="number"
                    inputMode="numeric"
                    min={6_000}
                    max={80_000}
                    placeholder="6000-80000"
                    value={targetTotalWordCount}
                    onChange={(event) => setTargetTotalWordCount(event.target.value)}
                  />
                  <small className="muted">留空时由模型根据故事和大纲决定；填写后也只作为创作倾向。</small>
                </label>
              </>
            ) : null}

            {storyLengthProfile === "long_serial" ? (
              <>
                <label className="stack">
                  <span>小说名称</span>
                  <input
                    className="input"
                    name="name"
                    placeholder="例如：青云山下有剑仙"
                    required
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                  />
                </label>
                <label className="stack">
                  <span>目标总字数</span>
                  <input
                    className="input"
                    name="targetTotalWordCount"
                    inputMode="numeric"
                    value={targetTotalWordCount}
                    onChange={(event) => setTargetTotalWordCount(event.target.value)}
                  />
                </label>
                <div className="onboarding-grid">
              <label className="stack">
                <span>题材/频道</span>
                <input
                  className="input"
                  name="genre"
                  placeholder="东方玄幻、都市异能、古言..."
                  value={genre}
                  onChange={(e) => setGenre(e.target.value)}
                />
              </label>
              <label className="stack">
                <span>主角一句话</span>
                <input
                  className="input"
                  name="protagonist"
                  placeholder="谁，想要什么，缺什么"
                  value={protagonist}
                  onChange={(e) => setProtagonist(e.target.value)}
                />
              </label>
                </div>
                <label className="stack">
              <span>作品简介</span>
              <textarea
                className="textarea"
                name="summary"
                placeholder="一句话讲清故事起点，后续大纲和智能写作会参考"
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
              />
                </label>
                <label className="stack">
              <span>核心卖点</span>
              <input
                className="input"
                name="coreSellingPoint"
                placeholder="这本书最值得追下去的点"
                value={coreSellingPoint}
                onChange={(e) => setCoreSellingPoint(e.target.value)}
              />
                </label>
                <div className="onboarding-grid">
              <label className="stack">
                <span>读者承诺</span>
                <input
                  className="input"
                  name="readerPromise"
                  placeholder="读者持续阅读会得到什么"
                  value={readerPromise}
                  onChange={(e) => setReaderPromise(e.target.value)}
                />
              </label>
              <label className="stack">
                <span>第一章目标</span>
                <input
                  className="input"
                  name="firstChapterGoal"
                  placeholder="本章必须完成的推进"
                  value={firstChapterGoal}
                  onChange={(e) => setFirstChapterGoal(e.target.value)}
                />
              </label>
                </div>
              </>
            ) : null}
            {error ? <p className="workspace-view-error" role="alert">{error}</p> : null}
            <div className="row">
              <button className="button" type="submit" disabled={pending || !canSubmit}>
                {pending
                  ? "创建中..."
                  : storyLengthProfile === "short_medium"
                    ? "创建并生成大纲"
                    : "新建长篇"}
              </button>
              <button className="button ghost" type="button" onClick={onClose} disabled={pending}>
                取消
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
