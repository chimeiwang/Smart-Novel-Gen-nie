import { afterEach, describe, it } from "node:test";
import assert from "node:assert/strict";

import { getAgentObservabilityConfig, getNonNegativeEnvInteger } from "../env";

const ORIGINAL_ENV = {
  LANGGRAPH_STUDIO_ENABLED: process.env.LANGGRAPH_STUDIO_ENABLED,
  WORKFLOW_EVENT_DEBUG_ENABLED: process.env.WORKFLOW_EVENT_DEBUG_ENABLED,
  LANGGRAPH_MEMORY_SAVER_TTL_MS: process.env.LANGGRAPH_MEMORY_SAVER_TTL_MS,
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

  it("keeps heavy debug surfaces disabled and uses a bounded checkpoint TTL by default", () => {
    delete process.env.LANGGRAPH_STUDIO_ENABLED;
    delete process.env.WORKFLOW_EVENT_DEBUG_ENABLED;
    delete process.env.LANGGRAPH_MEMORY_SAVER_TTL_MS;

    const config = getAgentObservabilityConfig();

    assert.equal(config.langGraphStudioEnabled, false);
    assert.equal(config.workflowEventDebugEnabled, false);
    assert.equal(config.langGraphMemorySaverTtlMs, 300_000);
  });

  it("enables heavy debug surfaces and accepts an explicit checkpoint TTL", () => {
    process.env.LANGGRAPH_STUDIO_ENABLED = "true";
    process.env.WORKFLOW_EVENT_DEBUG_ENABLED = "true";
    process.env.LANGGRAPH_MEMORY_SAVER_TTL_MS = "120000";

    const config = getAgentObservabilityConfig();

    assert.equal(config.langGraphStudioEnabled, true);
    assert.equal(config.workflowEventDebugEnabled, true);
    assert.equal(config.langGraphMemorySaverTtlMs, 120_000);
  });
});

describe("getNonNegativeEnvInteger", () => {
  it("parses a non-negative integer", () => {
    assert.equal(getNonNegativeEnvInteger("300000", 1), 300000);
    assert.equal(getNonNegativeEnvInteger("0", 1), 0);
  });

  it("falls back for invalid, negative, or fractional values", () => {
    assert.equal(getNonNegativeEnvInteger(undefined, 10), 10);
    assert.equal(getNonNegativeEnvInteger("-1", 10), 10);
    assert.equal(getNonNegativeEnvInteger("1.5", 10), 10);
    assert.equal(getNonNegativeEnvInteger("abc", 10), 10);
  });
});
