"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { browserApi } from "@/lib/api/browser";
import { requireApiData } from "@/lib/api/response";
import {
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
  const [name, setName] = useState("");
  const [summary, setSummary] = useState("");
  const [storyLengthProfile, setStoryLengthProfile] = useState<StoryLengthProfile>("long_serial");
  const [targetTotalWordCount, setTargetTotalWordCount] = useState("1000000");
  const [genre, setGenre] = useState("");
  const [protagonist, setProtagonist] = useState("");
  const [coreSellingPoint, setCoreSellingPoint] = useState("");
  const [readerPromise, setReaderPromise] = useState("");
  const [firstChapterGoal, setFirstChapterGoal] = useState("");

  const handleSubmit = async (formData: FormData) => {
    setPending(true);
    try {
      const result = requireApiData(await browserApi.POST("/api/v1/novels", {
        body: {
          name: String(formData.get("name") ?? ""),
          summary: String(formData.get("summary") ?? "") || null,
          storyLengthProfile,
          targetTotalWordCount: Number(targetTotalWordCount) || null,
          genre: genre || null,
          protagonist: protagonist || null,
          coreSellingPoint: coreSellingPoint || null,
          readerPromise: readerPromise || null,
          firstChapterGoal: firstChapterGoal || null,
        },
      }));
      onClose();
      router.push(`/workspace/${result.novelId}`);
      router.refresh();
    } finally {
      setPending(false);
    }
  };

  const selectStoryLengthProfile = (profile: StoryLengthProfile) => {
    setStoryLengthProfile(profile);
    setTargetTotalWordCount(profile === "short_medium" ? "80000" : "1000000");
  };

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
            <p className="muted">先补齐几个写作锚点。创建后会自动生成第一章、默认大纲、剧情进度和作品圣经。</p>
            <input type="hidden" name="storyLengthProfile" value={storyLengthProfile} />
            <label className="stack">
              <span>小说名称</span>
              <input
                className="input"
                name="name"
                placeholder="例如：青云山下有剑仙"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
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
                      <small>
                        {config.targetWords[0]}-{config.targetWords[1]} 字 · {config.chapterCount[0]}-{config.chapterCount[1]} 章
                      </small>
                    </button>
                  );
                })}
              </div>
            </div>
            <label className="stack">
              <span>目标总字数</span>
              <input
                className="input"
                name="targetTotalWordCount"
                inputMode="numeric"
                value={targetTotalWordCount}
                onChange={(e) => setTargetTotalWordCount(e.target.value)}
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
            <div className="row">
              <button className="button" type="submit" disabled={pending || !name.trim()}>
                {pending ? "创建中..." : "新建小说"}
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
