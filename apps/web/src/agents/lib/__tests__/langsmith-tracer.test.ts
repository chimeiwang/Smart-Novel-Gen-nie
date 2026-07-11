import { afterEach, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  __resetLangSmithTracerForTests,
  __setLangSmithTraceRunnerForTests,
  getTracingStats,
  initLangSmithTracer,
  traceTool,
} from "../langsmith-tracer";

const ORIGINAL_ENV = {
  LANGSMITH_API_KEY: process.env.LANGSMITH_API_KEY,
  LANGCHAIN_API_KEY: process.env.LANGCHAIN_API_KEY,
  LANGSMITH_PROJECT: process.env.LANGSMITH_PROJECT,
  LANGCHAIN_PROJECT: process.env.LANGCHAIN_PROJECT,
  LANGSMITH_TRACING: process.env.LANGSMITH_TRACING,
  LANGCHAIN_TRACING_V2: process.env.LANGCHAIN_TRACING_V2,
  LANGSMITH_TRACING_ENABLED: process.env.LANGSMITH_TRACING_ENABLED,
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

describe("langsmith-tracer", () => {
  beforeEach(() => {
    restoreEnv();
    __resetLangSmithTracerForTests();
  });

  afterEach(() => {
    __setLangSmithTraceRunnerForTests(null);
    __resetLangSmithTracerForTests();
    restoreEnv();
  });

  it("enables tracing when LANGSMITH_API_KEY and LANGSMITH_TRACING=true are configured", async () => {
    process.env.LANGSMITH_TRACING_ENABLED = "true";
    process.env.LANGSMITH_API_KEY = "test-key";
    process.env.LANGSMITH_PROJECT = "inkforge-test";
    process.env.LANGSMITH_TRACING = "true";

    await initLangSmithTracer();

    const stats = getTracingStats();
    assert.equal(stats.initialized, true);
    assert.equal(stats.enabled, true);
    assert.equal(stats.project, "inkforge-test");
    assert.equal(process.env.LANGCHAIN_TRACING_V2, "true");
  });

  it("also enables tracing from LangChain-compatible LANGCHAIN_TRACING_V2=true", async () => {
    process.env.LANGSMITH_TRACING_ENABLED = "true";
    process.env.LANGCHAIN_API_KEY = "test-key";
    process.env.LANGCHAIN_PROJECT = "inkforge-langchain";
    process.env.LANGCHAIN_TRACING_V2 = "true";
    delete process.env.LANGSMITH_TRACING;

    await initLangSmithTracer();

    const stats = getTracingStats();
    assert.equal(stats.initialized, true);
    assert.equal(stats.enabled, true);
    assert.equal(stats.project, "inkforge-langchain");
    assert.equal(process.env.LANGSMITH_TRACING, "true");
  });

  it("keeps tracing disabled when no LangSmith API key is configured", async () => {
    process.env.LANGSMITH_TRACING_ENABLED = "true";
    delete process.env.LANGSMITH_API_KEY;
    delete process.env.LANGCHAIN_API_KEY;
    process.env.LANGSMITH_TRACING = "true";

    await initLangSmithTracer();

    const stats = getTracingStats();
    assert.equal(stats.initialized, true);
    assert.equal(stats.enabled, false);
  });

  it("keeps tracing disabled unless the project-level switch is enabled", async () => {
    process.env.LANGSMITH_API_KEY = "test-key";
    process.env.LANGSMITH_TRACING = "true";
    delete process.env.LANGSMITH_TRACING_ENABLED;

    await initLangSmithTracer();

    const stats = getTracingStats();
    assert.equal(stats.initialized, true);
    assert.equal(stats.enabled, false);
  });

  it("wraps traced work with an injectable runner for deterministic tests", async () => {
    process.env.LANGSMITH_TRACING_ENABLED = "true";
    process.env.LANGSMITH_API_KEY = "test-key";
    process.env.LANGSMITH_TRACING = "true";
    await initLangSmithTracer();

    const calls: Array<{ name: string; metadata: Record<string, unknown> }> = [];
    __setLangSmithTraceRunnerForTests(async (name, metadata, fn) => {
      calls.push({ name, metadata });
      return fn();
    });

    const result = await traceTool("get_character_detail", { agentId: "写作" }, async () => "ok");

    assert.equal(result, "ok");
    assert.deepEqual(calls, [
      {
        name: "tool:get_character_detail",
        metadata: {
          agentId: "写作",
          service: "inkforge",
        },
      },
    ]);
  });
});
