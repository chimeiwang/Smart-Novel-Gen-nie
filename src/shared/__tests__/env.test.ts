import { afterEach, describe, it } from "node:test";
import assert from "node:assert/strict";

import { getAgentObservabilityConfig } from "../env";

const ORIGINAL_ENV = {
  LANGGRAPH_STUDIO_ENABLED: process.env.LANGGRAPH_STUDIO_ENABLED,
  WORKFLOW_EVENT_DEBUG_ENABLED: process.env.WORKFLOW_EVENT_DEBUG_ENABLED,
};

function restoreEnv() {
  for (const [key, value] of Object.entries(ORIGINAL_ENV)) {
    if (value === undefined) {
      delete process.env[key];
    } else {
      process.env[key] = value;
    }
  }
}

describe("getAgentObservabilityConfig", () => {
  afterEach(() => {
    restoreEnv();
  });

  it("keeps heavy debug surfaces disabled by default", () => {
    delete process.env.LANGGRAPH_STUDIO_ENABLED;
    delete process.env.WORKFLOW_EVENT_DEBUG_ENABLED;

    const config = getAgentObservabilityConfig();

    assert.equal(config.langGraphStudioEnabled, false);
    assert.equal(config.workflowEventDebugEnabled, false);
  });

  it("enables heavy debug surfaces only when explicitly configured", () => {
    process.env.LANGGRAPH_STUDIO_ENABLED = "true";
    process.env.WORKFLOW_EVENT_DEBUG_ENABLED = "true";

    const config = getAgentObservabilityConfig();

    assert.equal(config.langGraphStudioEnabled, true);
    assert.equal(config.workflowEventDebugEnabled, true);
  });
});
