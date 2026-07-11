"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { type AgentId } from "@/agents/client";
import { getDefaultSelectedAgents } from "@/features/writing/agent-selector";
import { WritingConversation } from "@/features/writing/writing-conversation";

type SmartWritingPanelProps = {
  novelId: string;
  currentChapter?: {
    id: string;
    title: string;
    status: string;
    wordCount: number;
    openConsistencyCheckCount: number;
    approvedBeatPlan: {
      id: string;
      chapterGoal: string;
      sceneCount: number;
      totalEstimatedWords: number;
    } | null;
  };
  defaultWordCount?: number;
};

export function SmartWritingPanel({
  novelId,
  currentChapter,
  defaultWordCount = 4000,
}: SmartWritingPanelProps) {
  const router = useRouter();

  const [selectedAgents] = useState<AgentId[]>(() => getDefaultSelectedAgents());
  const [targetWordCount] = useState(defaultWordCount);

  return (
    <div className="panel panel-flex">
      {currentChapter ? (
        <WritingConversation
          novelId={novelId}
          chapterId={currentChapter.id}
          chapterContext={currentChapter}
          selectedAgents={selectedAgents}
          targetWordCount={targetWordCount}
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
