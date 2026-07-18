import assert from "node:assert/strict";
import test from "node:test";

import {
  deriveShortStoryActions,
  isShortStoryInteractionLocked,
} from "../short-story/short-story-workflow-state";

test("没有大纲且没有进行中任务时只开放重试生成大纲", () => {
  assert.deepEqual(
    deriveShortStoryActions({
      targetWordCount: 20_000,
      outlineStatus: null,
      draftStatus: null,
      commandStatus: null,
      taskPhase: null,
    }),
    {
      canRetryOutline: true,
      canEditOutline: false,
      canDecideOutline: false,
      canGenerateDraft: false,
      canReviseDraft: false,
      canDecideDraft: false,
      canUpdateTargetWordCount: true,
      runFailed: false,
      targetWordCountValid: true,
    },
  );
});

test("大纲等待用户时允许编辑与决策，但未批准前不允许生成正文", () => {
  const actions = deriveShortStoryActions({
    targetWordCount: 20_000,
    outlineStatus: "awaiting_user",
    draftStatus: null,
    commandStatus: "succeeded",
    taskPhase: "awaiting_user",
  });

  assert.equal(actions.canEditOutline, true);
  assert.equal(actions.canDecideOutline, true);
  assert.equal(actions.canGenerateDraft, false);
});

test("只有已应用大纲且无进行中操作时才能生成完整初稿", () => {
  assert.equal(
    deriveShortStoryActions({
      targetWordCount: 20_000,
      outlineStatus: "applied",
      draftStatus: null,
      commandStatus: "succeeded",
      taskPhase: "completed",
    }).canGenerateDraft,
    true,
  );
  assert.equal(
    deriveShortStoryActions({
      targetWordCount: 20_000,
      outlineStatus: "applied",
      draftStatus: null,
      commandStatus: "processing",
      taskPhase: "active",
    }).canGenerateDraft,
    false,
  );
});

test("完整正文等待用户时开放返工和决策", () => {
  const actions = deriveShortStoryActions({
    targetWordCount: 80_000,
    outlineStatus: "applied",
    draftStatus: "awaiting_user",
    commandStatus: "succeeded",
    taskPhase: "awaiting_user",
  });

  assert.equal(actions.canReviseDraft, true);
  assert.equal(actions.canDecideDraft, true);
});

test("越界目标字数阻止启动大纲或正文", () => {
  for (const targetWordCount of [null, 5_999, 80_001]) {
    const withoutOutline = deriveShortStoryActions({
      targetWordCount,
      outlineStatus: null,
      draftStatus: null,
      commandStatus: null,
      taskPhase: null,
    });
    const withOutline = deriveShortStoryActions({
      targetWordCount,
      outlineStatus: "applied",
      draftStatus: null,
      commandStatus: null,
      taskPhase: "completed",
    });

    assert.equal(withoutOutline.targetWordCountValid, false);
    assert.equal(withoutOutline.canRetryOutline, false);
    assert.equal(withOutline.canGenerateDraft, false);
  }
});

test("旧中短篇存在多个历史 Chapter 时阻止全部新流程动作", () => {
  const withoutOutline = deriveShortStoryActions({
    targetWordCount: 20_000,
    chapterCount: 2,
    outlineStatus: null,
    draftStatus: null,
    commandStatus: null,
    taskPhase: null,
  });
  const withDraft = deriveShortStoryActions({
    targetWordCount: 20_000,
    chapterCount: 3,
    outlineStatus: "applied",
    draftStatus: "awaiting_user",
    commandStatus: "succeeded",
    taskPhase: "awaiting_user",
  });

  assert.equal(withoutOutline.canRetryOutline, false);
  assert.equal(withDraft.canEditOutline, false);
  assert.equal(withDraft.canDecideOutline, false);
  assert.equal(withDraft.canGenerateDraft, false);
  assert.equal(withDraft.canReviseDraft, false);
  assert.equal(withDraft.canDecideDraft, false);
});

test("首次权威 aggregate 成功前不能把未知状态当成无大纲", () => {
  const actions = deriveShortStoryActions({
    authoritativeStateReady: false,
    targetWordCount: 20_000,
    outlineStatus: null,
    draftStatus: null,
    commandStatus: null,
    taskPhase: null,
  });

  assert.equal(actions.canRetryOutline, false);
  assert.equal(actions.canGenerateDraft, false);
  assert.equal(actions.canUpdateTargetWordCount, false);
});

test("模型任务 active 或 waiting_call 时锁定全部 mutation", () => {
  assert.equal(isShortStoryInteractionLocked({
    pendingAction: null,
    commandStatus: "succeeded",
    taskPhase: "active",
  }), true);
  assert.equal(isShortStoryInteractionLocked({
    pendingAction: null,
    commandStatus: null,
    taskPhase: "waiting_call",
  }), true);
  assert.equal(isShortStoryInteractionLocked({
    pendingAction: null,
    commandStatus: "succeeded",
    taskPhase: "completed",
  }), false);

  assert.equal(deriveShortStoryActions({
    authoritativeStateReady: true,
    targetWordCount: 20_000,
    outlineStatus: "awaiting_user",
    draftStatus: null,
    commandStatus: "processing",
    taskPhase: "active",
  }).canUpdateTargetWordCount, false);
});

test("失败命令恢复旧稿后仍提示失败并允许用户处理旧稿", () => {
  const actions = deriveShortStoryActions({
    authoritativeStateReady: true,
    targetWordCount: 20_000,
    outlineStatus: "applied",
    draftStatus: "awaiting_user",
    commandStatus: "failed",
    taskPhase: "awaiting_user_review",
  });

  assert.equal(actions.runFailed, true);
  assert.equal(actions.canReviseDraft, true);
  assert.equal(actions.canDecideDraft, true);
});
