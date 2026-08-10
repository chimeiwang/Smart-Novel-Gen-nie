"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { AgentId } from "@/features/writing/agent-registry";
import { getDefaultSelectedAgents } from "@/features/writing/agent-selector";
import { WritingConversation } from "@/features/writing/writing-conversation";
import type { SelectionBridge } from "@/features/editor/selection-identity";
import { dispatchWorkspaceInvalidation } from "./workspace-invalidation";

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
  selectionBridge?: SelectionBridge;
};

export function SmartWritingPanel({
  novelId,
  currentChapter,
  defaultWordCount = 4000,
  selectionBridge,
}: SmartWritingPanelProps) {
  const router = useRouter();

  const [selectedAgents] = useState<AgentId[]>(() => getDefaultSelectedAgents());
  const [targetWordCount] = useState(defaultWordCount);

  return (
    <div className="panel panel-flex workspace-chat-panel">
      {currentChapter ? (
        <WritingConversation
          key={currentChapter.id}
          novelId={novelId}
          chapterId={currentChapter.id}
          chapterContext={currentChapter}
          selectedAgents={selectedAgents}
          targetWordCount={targetWordCount}
          selectionBridge={selectionBridge}
          onComplete={() => {
            dispatchWorkspaceInvalidation(novelId, ["lore", "planning", "resources"]);
            router.refresh();
          }}
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
