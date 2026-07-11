import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  buildWorkflowMessageMetadata,
  createWorkflowMessageDedupKey,
  shouldPersistWorkflowMessage,
} from "../workflow-message-store";

describe("workflow message store helpers", () => {
  it("builds stable metadata and dedup keys for workflow messages", () => {
    const metadata = buildWorkflowMessageMetadata({
      taskId: "task-1",
      eventType: "agent_done",
      agentId: "写作",
      content: "同一段回复",
    });

    assert.equal(metadata.taskId, "task-1");
    assert.equal(metadata.eventType, "agent_done");
    assert.equal(metadata.agentId, "写作");
    assert.equal(metadata.source, "workflow");
    assert.equal(
      createWorkflowMessageDedupKey(metadata),
      createWorkflowMessageDedupKey(
        buildWorkflowMessageMetadata({
          taskId: "task-1",
          eventType: "agent_done",
          agentId: "写作",
          content: "同一段回复",
        })
      )
    );
  });

  it("skips duplicate workflow messages with the same dedup key", () => {
    const metadata = buildWorkflowMessageMetadata({
      taskId: "task-1",
      eventType: "done",
      content: "完成",
    });
    const existingMetadata = JSON.stringify({
      source: "workflow",
      taskId: "task-1",
      eventType: "done",
      dedupKey: createWorkflowMessageDedupKey(metadata),
    });

    assert.equal(shouldPersistWorkflowMessage([existingMetadata], metadata), false);
  });

  it("does not treat frontend optimistic messages as workflow duplicates", () => {
    const metadata = buildWorkflowMessageMetadata({
      taskId: "task-1",
      eventType: "user",
      content: "继续",
    });

    assert.equal(
      shouldPersistWorkflowMessage(
        [JSON.stringify({ source: "frontend", taskId: "task-1", eventType: "user" })],
        metadata
      ),
      true
    );
  });
});
