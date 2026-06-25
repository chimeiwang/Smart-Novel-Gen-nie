import { afterEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { createWorkflowEventFileLogger } from "../workflow-event-log";

const ORIGINAL_ENV = {
  WORKFLOW_EVENT_LOG_ENABLED: process.env.WORKFLOW_EVENT_LOG_ENABLED,
};

function restoreEnv() {
  if (ORIGINAL_ENV.WORKFLOW_EVENT_LOG_ENABLED === undefined) {
    delete process.env.WORKFLOW_EVENT_LOG_ENABLED;
  } else {
    process.env.WORKFLOW_EVENT_LOG_ENABLED = ORIGINAL_ENV.WORKFLOW_EVENT_LOG_ENABLED;
  }
}

describe("WorkflowEventFileLogger", () => {
  afterEach(() => {
    restoreEnv();
  });

  it("is disabled by default unless enabled from .env", () => {
    delete process.env.WORKFLOW_EVENT_LOG_ENABLED;

    const logger = createWorkflowEventFileLogger({
      taskId: "task-1",
      runKind: "writing-workflow",
    });

    assert.equal(logger.isEnabledForTests(), false);
  });

  it("can be enabled from .env", () => {
    process.env.WORKFLOW_EVENT_LOG_ENABLED = "true";

    const logger = createWorkflowEventFileLogger({
      taskId: "task-1",
      runKind: "writing-workflow",
    });

    assert.equal(logger.isEnabledForTests(), true);
  });
});
