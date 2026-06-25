"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { updatePlotProgressAction } from "@/app/actions";

type ProgressPanelProps = {
  novelId: string;
  progress: {
    currentStage: string;
    currentGoal: string | null;
    currentConflict: string | null;
    nextMilestone: string | null;
  } | null;
};

export function ProgressPanel({ novelId, progress }: ProgressPanelProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [currentStage, setCurrentStage] = useState(progress?.currentStage ?? "开篇");
  const [currentGoal, setCurrentGoal] = useState(progress?.currentGoal ?? "");
  const [currentConflict, setCurrentConflict] = useState(progress?.currentConflict ?? "");
  const [nextMilestone, setNextMilestone] = useState(progress?.nextMilestone ?? "");

  const handleSave = () => {
    startTransition(async () => {
      await updatePlotProgressAction({
        novelId,
        currentStage,
        currentGoal,
        currentConflict,
        nextMilestone,
      });

      router.refresh();
    });
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <h3 className="title-md">剧情进度</h3>
          <p className="muted">AI 会优先参考这里判断现在该推进什么</p>
        </div>
      </div>
      <div className="panel-body stack">
        <input
          className="input"
          value={currentStage}
          onChange={(event) => setCurrentStage(event.target.value)}
          placeholder="当前阶段"
        />
        <input
          className="input"
          value={currentGoal}
          onChange={(event) => setCurrentGoal(event.target.value)}
          placeholder="当前目标"
        />
        <textarea
          className="textarea"
          value={currentConflict}
          onChange={(event) => setCurrentConflict(event.target.value)}
          placeholder="当前冲突"
        />
        <input
          className="input"
          value={nextMilestone}
          onChange={(event) => setNextMilestone(event.target.value)}
          placeholder="下一里程碑"
        />
        <button className="button secondary" type="button" onClick={handleSave}>
          {pending ? "保存中..." : "保存剧情进度"}
        </button>
      </div>
    </div>
  );
}
