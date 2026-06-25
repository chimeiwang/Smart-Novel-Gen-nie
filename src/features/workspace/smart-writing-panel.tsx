"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { type AgentId } from "@/agents/client";
import { AgentSelector, getDefaultSelectedAgents } from "@/features/writing/agent-selector";
import { WritingConversation } from "@/features/writing/writing-conversation";
import type { QualityCheckDto } from "@/shared/contracts/quality-check";

type SmartWritingPanelProps = {
  novelId: string;
  currentChapterId?: string;
  defaultWordCount?: number;
  chapterStatus?: string;
  qualityChecks?: QualityCheckDto[];
};

/**
 * 智能写作面板
 * 微信群聊样式
 */
export function SmartWritingPanel({
  novelId,
  currentChapterId,
  defaultWordCount = 4000,
  chapterStatus,
  qualityChecks = [],
}: SmartWritingPanelProps) {
  const router = useRouter();

  const [selectedAgents, setSelectedAgents] = useState<AgentId[]>(() => getDefaultSelectedAgents());
  const [targetWordCount, setTargetWordCount] = useState(defaultWordCount);

  return (
    <div className="panel panel-flex">
      {/* 配置面板（可折叠） */}
      {/* <AgentSelector
        selectedAgents={selectedAgents}
        onChange={setSelectedAgents}
        targetWordCount={targetWordCount}
        onWordCountChange={setTargetWordCount}
      /> */}

      {/* 聊天区域 */}
      {currentChapterId ? (
        <WritingConversation
          novelId={novelId}
          chapterId={currentChapterId}
          selectedAgents={selectedAgents}
          targetWordCount={targetWordCount}
          chapterStatus={chapterStatus}
          qualityChecks={qualityChecks}
          onComplete={() => router.refresh()}
        />
      ) : (
        <div className="empty-chat">
          <div className="empty-icon">📖</div>
          <div className="empty-text">请先选择一个章节</div>
        </div>
      )}
    </div>
  );
}
