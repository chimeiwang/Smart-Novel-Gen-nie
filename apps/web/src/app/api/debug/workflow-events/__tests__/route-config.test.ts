import { afterEach, describe, it } from "node:test";
import assert from "node:assert/strict";

import { isWorkflowEventDebugEnabled } from "../route";

const ORIGINAL_ENV = {
  WORKFLOW_EVENT_DEBUG_ENABLED: process.env.WORKFLOW_EVENT_DEBUG_ENABLED,
};

function restoreEnv() {
  if (ORIGINAL_ENV.WORKFLOW_EVENT_DEBUG_ENABLED === undefined) {
    delete process.env.WORKFLOW_EVENT_DEBUG_ENABLED;
  } else {
    process.env.WORKFLOW_EVENT_DEBUG_ENABLED = ORIGINAL_ENV.WORKFLOW_EVENT_DEBUG_ENABLED;
  }
}

describe("workflow event debug route config", () => {
  afterEach(() => {
    restoreEnv();
  });

  it("is hidden by default", () => {
    delete process.env.WORKFLOW_EVENT_DEBUG_ENABLED;

    assert.equal(isWorkflowEventDebugEnabled(), false);
  });

  it("is visible only when explicitly enabled", () => {
    process.env.WORKFLOW_EVENT_DEBUG_ENABLED = "true";

    assert.equal(isWorkflowEventDebugEnabled(), true);
  });
});
