import assert from "node:assert/strict";
import test from "node:test";

import {
  getAcceptedPollingStatus,
  getShortStoryPollDelay,
  shouldPollShortStory,
  shouldRefreshOnVisibilityChange,
} from "../short-story/short-story-polling";
import type { components } from "@inkforge/api-client";

type GeneratedCommandStatus = components["schemas"]["ShortStoryTaskStatus"]["latestCommandStatus"];
type GeneratedArtifactStatus = components["schemas"]["ShortStoryArtifactResponse"]["status"];

test("轮询状态类型与生成客户端契约保持一致", () => {
  const commandStatus: GeneratedCommandStatus = "processing";
  const artifactStatus: GeneratedArtifactStatus = "under_review";

  assert.equal(getAcceptedPollingStatus(commandStatus), "processing");
  assert.equal(shouldPollShortStory({
    commandStatus: null,
    taskPhase: "reviewing",
    artifactStatuses: [artifactStatus],
  }), true);
});

test("accepted 响应即使已经瞬时成功，也要等聚合状态确认后才停止轮询", () => {
  assert.equal(getAcceptedPollingStatus("submitted"), "submitted");
  assert.equal(getAcceptedPollingStatus("succeeded"), "pending");
  assert.equal(getAcceptedPollingStatus("failed"), "pending");
});

test("前台两秒轮询，后台十秒轮询", () => {
  assert.equal(getShortStoryPollDelay({ visible: true, consecutiveErrors: 0 }), 2_000);
  assert.equal(getShortStoryPollDelay({ visible: false, consecutiveErrors: 0 }), 10_000);
});

test("轮询错误按 2、4、8、15 秒退避并封顶", () => {
  assert.deepEqual(
    [1, 2, 3, 4, 9].map((consecutiveErrors) =>
      getShortStoryPollDelay({ visible: true, consecutiveErrors }),
    ),
    [2_000, 4_000, 8_000, 15_000, 15_000],
  );
});

test("命令、任务或草案仍在推进时继续轮询", () => {
  for (const commandStatus of ["pending", "submitted", "processing"] as const) {
    assert.equal(
      shouldPollShortStory({ commandStatus, taskPhase: "error", artifactStatuses: [] }),
      true,
    );
  }
  for (const taskPhase of ["active", "waiting_call"] as const) {
    assert.equal(
      shouldPollShortStory({ commandStatus: null, taskPhase, artifactStatuses: [] }),
      true,
    );
  }
  for (const artifactStatus of ["draft", "under_review", "applying"] as const) {
    assert.equal(
      shouldPollShortStory({
        commandStatus: null,
        taskPhase: "reviewing",
        artifactStatuses: [artifactStatus],
      }),
      true,
    );
  }
});

test("等待用户、已应用、完成或失败且没有活跃命令时停止轮询", () => {
  assert.equal(
    shouldPollShortStory({
      commandStatus: "succeeded",
      taskPhase: "awaiting_user",
      artifactStatuses: ["awaiting_user"],
    }),
    false,
  );
  assert.equal(
    shouldPollShortStory({
      commandStatus: null,
      taskPhase: "completed",
      artifactStatuses: ["applied"],
    }),
    false,
  );
  assert.equal(
    shouldPollShortStory({ commandStatus: "failed", taskPhase: "error", artifactStatuses: [] }),
    false,
  );
});

test("任务终态优先于残留的处理中草案状态", () => {
  for (const taskPhase of ["completed", "error"] as const) {
    for (const artifactStatus of ["draft", "under_review", "applying"] as const) {
      assert.equal(
        shouldPollShortStory({
          commandStatus: "failed",
          taskPhase,
          artifactStatuses: [artifactStatus],
        }),
        false,
      );
    }
  }

  assert.equal(
    shouldPollShortStory({
      commandStatus: "processing",
      taskPhase: "error",
      artifactStatuses: ["under_review"],
    }),
    true,
  );
});

test("页面从后台回到前台时立即刷新", () => {
  assert.equal(shouldRefreshOnVisibilityChange(false, true), true);
  assert.equal(shouldRefreshOnVisibilityChange(true, true), false);
  assert.equal(shouldRefreshOnVisibilityChange(true, false), false);
});
