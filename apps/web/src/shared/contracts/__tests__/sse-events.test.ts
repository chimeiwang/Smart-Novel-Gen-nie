/**
 * SSE event contract tests.
 *
 * 运行方式：npx tsx --test src/shared/contracts/__tests__/sse-events.test.ts
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { parseSseEvent, SSE_EVENT_TYPES } from "../sse-events";

describe("SSE event contract", () => {
  it("uses the standard SSE event field when data omits type", () => {
    const event = parseSseEvent(
      {
        agentId: "剧情",
        artifactId: "artifact-1",
      },
      "artifact_awaiting_user_approval",
    );

    assert.equal(event?.type, "artifact_awaiting_user_approval");
    assert.equal(event?.artifactId, "artifact-1");
  });

  it("parses agent status tool result summaries", () => {
    const event = parseSseEvent({
      type: "agent_status",
      agentId: "编辑",
      status: "querying",
      toolName: "get_novel_info",
      resultSummary: "作品《遗产猎人》 · 当前章《第一章 遗孤与遗产》",
      detailsHidden: true,
    });

    assert.equal(event?.type, "agent_status");
    assert.equal(event?.resultSummary, "作品《遗产猎人》 · 当前章《第一章 遗孤与遗产》");
  });

  it("parses update builder status events", () => {
    const started = parseSseEvent({
      type: "update_builder_started",
      agentId: "剧情",
      artifactKey: "outline-builder-1",
      summary: "批量重构大纲",
    });
    assert.equal(started?.type, "update_builder_started");

    const validationFailed = parseSseEvent({
      type: "update_builder_validation_failed",
      agentId: "剧情",
      artifactKey: "outline-builder-1",
      errors: ["outlineAdjustments.0.parentKey: 找不到父节点"],
    });
    assert.equal(validationFailed?.type, "update_builder_validation_failed");

    const outlineTreeAppended = parseSseEvent({
      type: "update_builder_outline_tree_appended",
      agentId: "剧情",
      artifactKey: "outline-builder-1",
      stageCount: 1,
      nodeCount: 3,
    });
    assert.equal(outlineTreeAppended?.type, "update_builder_outline_tree_appended");
  });

  it("lists update builder event types", () => {
    assert.ok(SSE_EVENT_TYPES.includes("update_builder_started"));
    assert.ok(SSE_EVENT_TYPES.includes("update_builder_batch_appended"));
    assert.ok(SSE_EVENT_TYPES.includes("update_builder_outline_tree_appended"));
    assert.ok(SSE_EVENT_TYPES.includes("update_builder_text_put"));
    assert.ok(SSE_EVENT_TYPES.includes("update_builder_validation_failed"));
  });

  it("parses review artifact display request events", () => {
    const event = parseSseEvent({
      type: "review_artifact_requested",
      agentId: "剧情",
      artifactId: "artifact-1",
      artifact: { id: "artifact-1", status: "awaiting_user" },
      reason: "草案已生成，请展示给用户确认。",
    });

    assert.equal(event?.type, "review_artifact_requested");
    assert.ok(SSE_EVENT_TYPES.includes("review_artifact_requested"));
  });
});
