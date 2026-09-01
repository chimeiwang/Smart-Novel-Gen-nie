/**
 * SSE event contract tests.
 *
 * 运行方式：npx tsx --test src/shared/contracts/__tests__/sse-events.test.ts
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { parseSseEvent, SSE_EVENT_TYPES } from "../sse-events";

const SHA = "a".repeat(64);

function modelProfile(profile = "writer.chapter_selection.v1") {
  return {
    profile,
    version: 1,
    reasoningMode: "bounded",
    deploymentProfileKey: `deployment.${profile}`,
    promptProfile: {
      name: `prompt.${profile}`,
      version: 1,
      sha256: SHA,
    },
  };
}

function resolvedModel(profile = modelProfile()) {
  return {
    deploymentProfileKey: profile.deploymentProfileKey,
    deploymentFingerprint: SHA,
    provider: "deepseek",
    model: "deepseek-chat",
    transportProfile: "transport.responses.v1",
    endpointProfile: "endpoint.default.v1",
    structuredOutputRoute: "responses_json_schema_v1",
    capabilityVersion: "capability.structured.v1",
    reasoningMode: profile.reasoningMode,
    supportsRequestIdempotency: true,
  };
}

describe("SSE event contract", () => {
  it("解析无游标的权威运行结果控制帧", () => {
    const event = parseSseEvent(
      {
        state: "inconsistent",
        code: "SHORT_MEDIUM_RESULT_MISSING",
        taskTerminal: true,
        streamShouldClose: true,
        reconciliationRequired: true,
        currentCommand: null,
        result: { kind: "short_candidate", ready: false, id: null },
        observedAt: "2026-08-01T12:00:00Z",
      },
      "run_outcome",
    );

    assert.equal(event?.type, "run_outcome");
    assert.equal(event?.state, "inconsistent");
    assert.equal(event?.result.ready, false);
    assert.ok(SSE_EVENT_TYPES.includes("run_outcome"));
  });

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

  it("rejects malformed agent start events", () => {
    assert.equal(parseSseEvent({ phase: "active" }, "agent_start"), null);
    assert.equal(
      parseSseEvent(
        { agentId: "写作", agentName: "作家" },
        "agent_start",
      )?.type,
      "agent_start",
    );
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

  it("解析 V2 snapshot 并拒绝不一致的 baseSequence", () => {
    const raw = {
      protocolVersion: "2.0",
      engineVersion: 2,
      runId: "run-1",
      baseSequence: 4,
      snapshot: {
        workflow: "long_serial",
        operation: "rewrite_chapter_selection",
        status: "running",
        activeSteps: [],
        currentStep: null,
        cancelRequestedAt: null,
        lastEventSequence: 4,
        revision: 2,
        artifact: null,
        error: null,
      },
    };

    assert.equal(parseSseEvent(raw, "run_snapshot")?.type, "run_snapshot");
    assert.equal(
      parseSseEvent({ ...raw, baseSequence: 3 }, "run_snapshot"),
      null,
    );
    assert.ok(SSE_EVENT_TYPES.includes("run_snapshot"));
  });

  it("按 envelope 自带 eventType 解析 V2 progress", () => {
    const profile = modelProfile();
    const event = parseSseEvent({
      protocolVersion: "2.0",
      engineVersion: 2,
      runId: "run-1",
      sequence: 5,
      eventType: "step_progress",
      occurredAt: "2026-09-01T12:00:00Z",
      payload: {
        stepId: "step-1",
        fencingToken: 2,
        progressSequence: 3,
        modelProfile: profile,
        resolvedModel: resolvedModel(profile),
        phase: "waiting_provider",
        elapsedSeconds: 61,
        waitingOnProvider: true,
        usageStatus: "partial",
      },
    }, "step_progress");

    assert.equal(event?.type, "workflow_event");
    if (!event || event.type !== "workflow_event") return;
    assert.equal(event.eventType, "step_progress");
    assert.equal(event.payload.elapsedSeconds, 61);
    assert.ok(SSE_EVENT_TYPES.includes("workflow_event"));
  });

  it("V2 snapshot 严格校验 activeSteps、兼容摘要与模型身份", () => {
    const profile = modelProfile("reviewer.consistency.v1");
    const currentStep = {
      stepId: "step-review-1",
      ordinal: 2,
      purpose: "review",
      lane: "creative",
      modelProfile: profile,
      resolvedModel: resolvedModel(profile),
      status: "running",
      attemptCount: 1,
      fencingToken: 1,
      latestProgress: {
        progressSequence: 3,
        phase: "waiting_provider",
        elapsedSeconds: 61,
        waitingOnProvider: true,
        usageStatus: "partial",
      },
      errorCode: null,
    };
    const raw = {
      protocolVersion: "2.0",
      engineVersion: 2,
      runId: "run-1",
      baseSequence: 4,
      snapshot: {
        workflow: "long_serial",
        operation: "rewrite_chapter_selection",
        status: "running",
        activeSteps: [currentStep],
        currentStep,
        cancelRequestedAt: null,
        lastEventSequence: 4,
        revision: 2,
        artifact: null,
        error: null,
      },
    };

    assert.equal(parseSseEvent(raw, "run_snapshot")?.type, "run_snapshot");
    assert.equal(parseSseEvent({
      ...raw,
      snapshot: { ...raw.snapshot, currentStep: null },
    }, "run_snapshot"), null);
    const secondProfile = modelProfile("reviewer.editorial.v1");
    const secondStep = {
      ...currentStep,
      stepId: "step-review-2",
      ordinal: 3,
      modelProfile: secondProfile,
      resolvedModel: resolvedModel(secondProfile),
    };
    assert.equal(parseSseEvent({
      ...raw,
      snapshot: {
        ...raw.snapshot,
        activeSteps: [currentStep, secondStep],
        currentStep: secondStep,
      },
    }, "run_snapshot"), null);
    assert.equal(parseSseEvent({
      ...raw,
      snapshot: {
        ...raw.snapshot,
        activeSteps: [{ ...currentStep, resolvedModel: null }],
        currentStep: { ...currentStep, resolvedModel: null },
      },
    }, "run_snapshot"), null);
    assert.equal(parseSseEvent({
      ...raw,
      snapshot: {
        ...raw.snapshot,
        activeSteps: [{ ...currentStep, latestProgress: undefined }],
        currentStep: { ...currentStep, latestProgress: undefined },
      },
    }, "run_snapshot"), null);
    assert.equal(parseSseEvent({
      ...raw,
      snapshot: {
        ...raw.snapshot,
        activeSteps: [{
          ...currentStep,
          status: "pending",
          resolvedModel: null,
        }],
        currentStep: {
          ...currentStep,
          status: "pending",
          resolvedModel: null,
        },
      },
    }, "run_snapshot"), null);
  });

  it("V2 progress 拒绝缺失或错配的逻辑与解析模型身份", () => {
    const profile = modelProfile();
    const valid = {
      protocolVersion: "2.0",
      engineVersion: 2,
      runId: "run-1",
      sequence: 5,
      eventType: "step_progress",
      occurredAt: "2026-09-01T12:00:00Z",
      payload: {
        stepId: "step-1",
        fencingToken: 2,
        progressSequence: 3,
        modelProfile: profile,
        resolvedModel: resolvedModel(profile),
        phase: "validating",
        elapsedSeconds: 61,
        waitingOnProvider: false,
        usageStatus: "complete",
      },
    };

    assert.equal(parseSseEvent(valid)?.type, "workflow_event");
    const { modelProfile: _omitted, ...withoutProfile } = valid.payload;
    assert.equal(parseSseEvent({ ...valid, payload: withoutProfile }), null);
    assert.equal(parseSseEvent({
      ...valid,
      payload: {
        ...valid.payload,
        resolvedModel: {
          ...valid.payload.resolvedModel,
          deploymentProfileKey: "deployment.other.v1",
        },
      },
    }), null);
  });

  it("V2 review_started 携带稳定 pending Reviewer，step_finished 严格约束终态", () => {
    const consistency = modelProfile("reviewer.consistency.v1");
    const editorial = modelProfile("reviewer.editorial.v1");
    const reviewerSteps = [
      {
        stepId: "step-review-1",
        ordinal: 2,
        purpose: "review",
        lane: "interactive",
        modelProfile: consistency,
        status: "pending",
        attemptCount: 0,
        fencingToken: 0,
      },
      {
        stepId: "step-review-2",
        ordinal: 3,
        purpose: "review",
        lane: "interactive",
        modelProfile: editorial,
        status: "pending",
        attemptCount: 0,
        fencingToken: 0,
      },
    ];
    const reviewStarted = {
      protocolVersion: "2.0",
      engineVersion: 2,
      runId: "run-1",
      sequence: 6,
      eventType: "review_started",
      occurredAt: "2026-09-01T12:00:00Z",
      payload: {
        artifactId: "artifact-1",
        artifactRevision: 1,
        reviewerSteps,
      },
    };

    assert.equal(parseSseEvent(reviewStarted)?.type, "workflow_event");
    assert.equal(parseSseEvent({
      ...reviewStarted,
      payload: { ...reviewStarted.payload, reviewerSteps: [...reviewerSteps].reverse() },
    }), null);
    assert.equal(parseSseEvent({
      ...reviewStarted,
      payload: {
        ...reviewStarted.payload,
        reviewerSteps: [{ ...reviewerSteps[0], fencingToken: 1 }],
      },
    }), null);

    const finished = {
      protocolVersion: "2.0",
      engineVersion: 2,
      runId: "run-1",
      sequence: 7,
      eventType: "step_finished",
      occurredAt: "2026-09-01T12:00:01Z",
      payload: {
        stepId: "step-review-1",
        fencingToken: 1,
        status: "completed",
        errorCode: null,
      },
    };
    assert.equal(parseSseEvent(finished)?.type, "workflow_event");
    assert.equal(parseSseEvent({
      ...finished,
      payload: { ...finished.payload, status: "failed" },
    }), null);
    assert.equal(parseSseEvent({
      ...finished,
      payload: { ...finished.payload, errorCode: "MODEL_TIMEOUT" },
    }), null);
  });

  it("parses every shared Python and TypeScript event example", async () => {
    const fixtureUrl = new URL(
      "../../../../../../packages/service-contracts/contracts/writing-sse-events.json",
      import.meta.url,
    );
    const examples = JSON.parse(await readFile(fixtureUrl, "utf8")) as Array<{
      event: string;
      envelope: { data: Record<string, unknown> };
    }>;

    for (const example of examples) {
      const parsed = parseSseEvent(example.envelope.data, example.event);
      assert.ok(parsed, `无法解析共享事件 ${example.event}`);
      assert.equal(parsed.type, example.event);
    }
  });
});
