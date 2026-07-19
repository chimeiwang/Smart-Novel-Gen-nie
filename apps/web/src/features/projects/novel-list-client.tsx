"use client";

import type { components } from "@inkforge/api-client";
import Link from "next/link";
import { useState } from "react";

import { CreateNovelModal } from "@/features/projects/create-novel-modal";
import { LogoutButton } from "@/features/auth/user-menu";
import { STORY_LENGTH_PROFILE_CONFIG } from "@/shared/contracts/story-length-profile";

interface NovelListClientProps {
  novels: components["schemas"]["DashboardNovel"][];
}

export function NovelListClient({ novels }: NovelListClientProps) {
  const [showModal, setShowModal] = useState(false);

  return (
    <>
      <main className="page stack">
        <div className="row row-between home-header">
          <div>
            <div className="home-kicker">InkForge</div>
            <h1 className="title-xl">墨铸写作工作台</h1>
            <p className="home-subtitle">管理作品、章节、设定和 AI 协作流程。</p>
          </div>
          <div className="row">
            <button className="button" type="button" onClick={() => setShowModal(true)}>
              新建小说
            </button>
            <Link href="/styles" className="button ghost">
              文风库
            </Link>
            <Link href="/billing" className="button ghost">
              充值
            </Link>
            <LogoutButton />
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <div>
              <h2 className="title-lg">我的小说</h2>
              <p className="muted">点击任意作品进入创作工作台</p>
            </div>
          </div>
          <div className="panel-body">
            <div className="card-list">
              {novels.length > 0 ? (
                novels.map((novel) => (
                  <Link
                    key={novel.id}
                    href={`/workspace/${novel.id}?chapterId=${novel.chapters[0]?.id ?? ""}`}
                    className="card novel-card"
                  >
                    <div className="meta">
                      <span className="badge">
                        {STORY_LENGTH_PROFILE_CONFIG[novel.storyLengthProfile].label}
                      </span>
                      {novel.targetTotalWordCount ? (
                        <span className="badge">目标 {novel.targetTotalWordCount} 字</span>
                      ) : null}
                      {novel.storyLengthProfile === "long_serial" ? (
                        <span className="badge">{novel.chapters.length} 章</span>
                      ) : null}
                      {novel.appliedStyle && (
                        <span className="badge">文风：{novel.appliedStyle.name}</span>
                      )}
                    </div>
                    <div className="title-lg novel-card-title">{novel.name}</div>
                    <div className="novel-card-summary">{novel.summary || "暂无简介"}</div>
                  </Link>
                ))
              ) : (
                <div className="empty">
                  还没有小说，点击上方「新建小说」开始创作。
                </div>
              )}
            </div>
          </div>
        </div>
      </main>

      <CreateNovelModal isOpen={showModal} onClose={() => setShowModal(false)} />
    </>
  );
}
