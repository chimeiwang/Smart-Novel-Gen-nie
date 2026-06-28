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
  const [draft, setDraft] = useState<ProgressPanelProps["progress"] | null>(null);
  const currentStage = draft?.currentStage ?? progress?.currentStage ?? "开篇";
  const currentGoal = draft?.currentGoal ?? progress?.currentGoal ?? "";
  const currentConflict = draft?.currentConflict ?? progress?.currentConflict ?? "";
  const nextMilestone = draft?.nextMilestone ?? progress?.nextMilestone ?? "";

  const setField = (field: keyof NonNullable<ProgressPanelProps["progress"]>, value: string) => {
    setDraft((current) => ({
      currentStage,
      currentGoal,
      currentConflict,
      nextMilestone,
      ...current,
      [field]: value,
    }));
  };

  const handleSave = () => {
    startTransition(async () => {
      await updatePlotProgressAction({
        novelId,
        currentStage,
        currentGoal,
        currentConflict,
        nextMilestone,
      });

      setDraft(null);
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
          onChange={(event) => setField("currentStage", event.target.value)}
          placeholder="当前阶段"
        />
        <input
          className="input"
          value={currentGoal}
          onChange={(event) => setField("currentGoal", event.target.value)}
          placeholder="当前目标"
        />
        <textarea
          className="textarea"
          value={currentConflict}
          onChange={(event) => setField("currentConflict", event.target.value)}
          placeholder="当前冲突"
        />
        <input
          className="input"
          value={nextMilestone}
          onChange={(event) => setField("nextMilestone", event.target.value)}
          placeholder="下一里程碑"
        />
        <button className="button secondary" type="button" onClick={handleSave}>
          {pending ? "保存中..." : "保存剧情进度"}
        </button>
      </div>
    </div>
  );
}
