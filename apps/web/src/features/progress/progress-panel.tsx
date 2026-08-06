"use client";

import type { components } from "@inkforge/api-client";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import {
  advanceSingletonEditBaseline,
  createSingletonEditBaseline,
  markSingletonEditDirty,
  observeSingletonEditVersion,
  resolveSingletonEditValue,
} from "@/features/workspace/singleton-edit-baseline";
import { browserApi } from "@/lib/api/browser";
import { ApiResponseError, requireApiData } from "@/lib/api/response";

type PlotProgressDto = components["schemas"]["PlotProgressDto"];
type PlotProgressDraft = {
  currentStage: PlotProgressDto["currentStage"];
  currentGoal: NonNullable<PlotProgressDto["currentGoal"]>;
  currentConflict: NonNullable<PlotProgressDto["currentConflict"]>;
  nextMilestone: NonNullable<PlotProgressDto["nextMilestone"]>;
};

type ProgressPanelProps = {
  novelId: string;
  progress: PlotProgressDto | null;
  onChanged?: () => void;
};

export function ProgressPanel({ novelId, progress, onChanged }: ProgressPanelProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [draft, setDraft] = useState<PlotProgressDraft | null>(null);
  const [editBaseline, setEditBaseline] = useState(() => (
    createSingletonEditBaseline(progress?.updatedAt ?? null)
  ));
  const [saveError, setSaveError] = useState<string | null>(null);
  const currentEditBaseline = observeSingletonEditVersion(
    editBaseline,
    progress?.updatedAt ?? null,
  );
  const remoteDraft: PlotProgressDraft = {
    currentStage: progress?.currentStage ?? "开篇",
    currentGoal: progress?.currentGoal ?? "",
    currentConflict: progress?.currentConflict ?? "",
    nextMilestone: progress?.nextMilestone ?? "",
  };
  const currentDraft = resolveSingletonEditValue(
    currentEditBaseline,
    draft ?? remoteDraft,
    remoteDraft,
  );
  const { currentStage, currentGoal, currentConflict, nextMilestone } = currentDraft;

  const setField = (field: keyof PlotProgressDraft, value: string) => {
    setDraft({
      ...currentDraft,
      [field]: value,
    });
    setEditBaseline(markSingletonEditDirty(currentEditBaseline));
  };

  const handleSave = () => {
    startTransition(async () => {
      setSaveError(null);
      try {
        const saved = requireApiData(await browserApi.PUT("/api/v1/novels/{novel_id}/plot-progress", {
          params: { path: { novel_id: novelId } },
          body: {
            currentStage,
            currentGoal,
            currentConflict,
            nextMilestone,
            expectedUpdatedAt: currentEditBaseline.expectedUpdatedAt,
          },
        }));

        setEditBaseline((current) => advanceSingletonEditBaseline(
          observeSingletonEditVersion(current, progress?.updatedAt ?? null),
          saved.updatedAt,
        ));
        onChanged?.();
        router.refresh();
      } catch (error) {
        if (error instanceof ApiResponseError && error.status === 409) {
          setSaveError("资料已在其他位置更新，当前草稿已保留，请刷新资料后再保存。");
        } else {
          setSaveError(error instanceof Error ? error.message : "保存失败，请稍后重试。");
        }
      }
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
          disabled={pending}
          onChange={(event) => setField("currentStage", event.target.value)}
          placeholder="当前阶段"
        />
        <input
          className="input"
          value={currentGoal}
          disabled={pending}
          onChange={(event) => setField("currentGoal", event.target.value)}
          placeholder="当前目标"
        />
        <textarea
          className="textarea"
          value={currentConflict}
          disabled={pending}
          onChange={(event) => setField("currentConflict", event.target.value)}
          placeholder="当前冲突"
        />
        <input
          className="input"
          value={nextMilestone}
          disabled={pending}
          onChange={(event) => setField("nextMilestone", event.target.value)}
          placeholder="下一里程碑"
        />
        <button className="button secondary" type="button" disabled={pending} onClick={handleSave}>
          {pending ? "保存中..." : "保存剧情进度"}
        </button>
        {saveError ? <p className="form-error" role="alert">{saveError}</p> : null}
      </div>
    </div>
  );
}
