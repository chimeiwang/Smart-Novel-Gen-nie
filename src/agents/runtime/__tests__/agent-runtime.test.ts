/**
 * AgentRuntime 单元测试
 *
 * Phase 1：验证 AgentRuntimeImpl 的控制工具拦截逻辑和返回值结构。
 * 使用 Node 原生 test runner + tsx。
 *
 * 运行方式：npx tsx --test src/agents/runtime/__tests__/agent-runtime.test.ts
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import type OpenAI from "openai";
import "@/agents/tools";
import { AgentRuntimeImpl } from "../agent-runtime";
import { LegacyOpenAIRuntime, type ModelRuntimePort, type ToolCallTurnOptions } from "../model-runtime";
import {
  __resetLangSmithTracerForTests,
  __setLangSmithTraceRunnerForTests,
  initLangSmithTracer,
} from "@/agents/lib/langsmith-tracer";
import {
  formatControlToolValidationMessage,
  parseControlEventArgs,
  parseControlEventArgsDetailed,
} from "@/shared/contracts/agent-control";
import { getOpenAITools } from "@/agents/tools/registry";
import type { AgentRuntimeOptions, AgentRuntime } from "../agent-runtime";
import type { AgentTurnResult } from "../turn-result";

function createBillingStub() {
  return {
    ensureCanStartModelCall: async () => ({ maxOutputTokens: 1024 }),
    chargeAiUsage: async () => {},
  };
}

function createTestRuntime(client: unknown): AgentRuntimeImpl {
  return new AgentRuntimeImpl({
    runtime: new LegacyOpenAIRuntime({
      client: client as never,
      isAiConfigured: () => true,
      billing: createBillingStub(),
    }),
  });
}

function createStream(chunks: unknown[]): AsyncIterable<unknown> {
  return {
    async *[Symbol.asyncIterator]() {
      for (const chunk of chunks) {
        yield chunk;
      }
    },
  };
}

function createToolCallStream(
  toolName: string,
  args: Record<string, unknown>,
  content = ""
): AsyncIterable<unknown> {
  return createStream([
    {
      choices: [
        {
          delta: {
            content,
            tool_calls: [
              {
                index: 0,
                id: `call_${toolName}`,
                function: {
                  name: toolName,
                  arguments: JSON.stringify(args),
                },
              },
            ],
          },
          finish_reason: "tool_calls",
        },
      ],
    },
  ]);
}

function createMultiToolCallStream(
  toolCalls: Array<{ toolName: string; args: Record<string, unknown> }>,
  content = ""
): AsyncIterable<unknown> {
  return createStream([
    {
      choices: [
        {
          delta: {
            content,
            tool_calls: toolCalls.map((toolCall, index) => ({
              index,
              id: `call_${toolCall.toolName}_${index}`,
              function: {
                name: toolCall.toolName,
                arguments: JSON.stringify(toolCall.args),
              },
            })),
          },
          finish_reason: "tool_calls",
        },
      ],
    },
  ]);
}

function createRawToolCallStream(
  toolName: string,
  rawArguments: string,
  content = ""
): AsyncIterable<unknown> {
  return createStream([
    {
      choices: [
        {
          delta: {
            content,
            tool_calls: [
              {
                index: 0,
                id: `call_${toolName}`,
                function: {
                  name: toolName,
                  arguments: rawArguments,
                },
              },
            ],
          },
          finish_reason: "tool_calls",
        },
      ],
    },
  ]);
}

function createTextStream(content: string): AsyncIterable<unknown> {
  return createStream([
    {
      choices: [
        {
          delta: { content },
          finish_reason: "stop",
        },
      ],
    },
  ]);
}

function createMockClient(streams: AsyncIterable<unknown>[]) {
  let calls = 0;
  return {
    get calls() {
      return calls;
    },
    chat: {
      completions: {
        create: async () => {
          const stream = streams[calls];
          calls += 1;
          if (!stream) {
            throw new Error("unexpected extra LLM call");
          }
          return stream;
        },
      },
    },
  };
}

function createRuntimeOptions(): AgentRuntimeOptions {
  return {
    messages: [
      { role: "system", content: "你是测试 Agent" },
      { role: "user", content: "测试控制工具" },
    ],
    tools: getOpenAITools([
      "propose_updates",
      "get_novel_info",
      "list_outline_summary",
      "get_character_detail",
    ]),
    toolExecutor: async () => "read ok",
    metadata: { callType: "test" },
  };
}

async function withEnabledLangSmithForTest(fn: () => Promise<void>): Promise<void> {
  const original = {
    LANGSMITH_API_KEY: process.env.LANGSMITH_API_KEY,
    LANGSMITH_TRACING: process.env.LANGSMITH_TRACING,
    LANGSMITH_TRACING_ENABLED: process.env.LANGSMITH_TRACING_ENABLED,
  };
  process.env.LANGSMITH_API_KEY = "test-key";
  process.env.LANGSMITH_TRACING = "true";
  process.env.LANGSMITH_TRACING_ENABLED = "true";
  __resetLangSmithTracerForTests();
  await initLangSmithTracer();
  try {
    await fn();
  } finally {
    __setLangSmithTraceRunnerForTests(null);
    __resetLangSmithTracerForTests();
    if (original.LANGSMITH_API_KEY === undefined) delete process.env.LANGSMITH_API_KEY;
    else process.env.LANGSMITH_API_KEY = original.LANGSMITH_API_KEY;
    if (original.LANGSMITH_TRACING === undefined) delete process.env.LANGSMITH_TRACING;
    else process.env.LANGSMITH_TRACING = original.LANGSMITH_TRACING;
    if (original.LANGSMITH_TRACING_ENABLED === undefined) delete process.env.LANGSMITH_TRACING_ENABLED;
    else process.env.LANGSMITH_TRACING_ENABLED = original.LANGSMITH_TRACING_ENABLED;
  }
}

// ============================================
// 1. parseControlEventArgs 纯函数测试
// ============================================

describe("parseControlEventArgs", () => {
  it("解析 submit_quality_report → QualityReportEvent", () => {
    const event = parseControlEventArgs("submit_quality_report", {
      scores: { hook: 8, tension: 7, overall: 7 },
      qualityGate: "revise",
      rewriteBrief: "中段冲突不够激烈",
    });
    assert.ok(event);
    assert.equal(event!.type, "submit_quality_report");
    if (event!.type === "submit_quality_report") {
      assert.equal(event!.scores.hook, 8);
      assert.equal(event!.qualityGate, "revise");
    }
  });

  it("解析 propose_updates → ProposalUpdatesEvent", () => {
    const event = parseControlEventArgs("propose_updates", {
      summary: "新增角色「张三」并更新地点「长安城」的描述",
      updates: {
        characters: [
          { action: "create", name: "张三", personality: "勇敢果断", identity: "侠客" },
        ],
        locations: [
          { action: "update", name: "长安城", description: "繁华的唐代都城，人口百万" },
        ],
      },
    });
    assert.ok(event);
    assert.equal(event!.type, "propose_updates");
    if (event!.type === "propose_updates") {
      assert.ok(event!.updates, "应包含 updates payload");
      assert.equal(event!.summary, "新增角色「张三」并更新地点「长安城」的描述");
    }
  });

  it("propose_updates 拒绝缺少结构字段的大纲创建", () => {
    const result = parseControlEventArgsDetailed("propose_updates", {
      summary: "生成结构化大纲",
      updates: {
        outlineAdjustments: [
          { action: "create", title: "只有标题的大纲节点" },
        ],
      },
    });

    assert.equal(result.success, false);
    if (result.success) return;
    assert.ok(result.error.issues.some((issue) => issue.path.endsWith("kind")));
  });

  it("解析 begin_artifact_output → BeginArtifactOutputEvent", () => {
    const event = parseControlEventArgs("begin_artifact_output", {
      kind: "outline_draft",
      summary: "前十章大纲修改草案",
      artifactKey: "outline-long-draft",
      reviewerAgent: "编辑",
      submitForReview: true,
    });
    assert.ok(event);
    assert.equal(event!.type, "begin_artifact_output");
    if (event!.type === "begin_artifact_output") {
      assert.equal(event.kind, "outline_draft");
      assert.equal(event.artifactKey, "outline-long-draft");
      assert.equal(event.reviewerAgent, "编辑");
    }
  });

  it("解析 show_review_artifact 支持 artifactKey", () => {
    const event = parseControlEventArgs("show_review_artifact", {
      artifactKey: "outline-revision-1",
      reason: "草案已生成，请展示给用户确认。",
    });
    assert.ok(event);
    assert.equal(event!.type, "show_review_artifact");
    if (event!.type === "show_review_artifact") {
      assert.equal(event.artifactKey, "outline-revision-1");
      assert.equal(event.artifactId, undefined);
    }
  });

  it("show_review_artifact 拒绝缺少 artifactId 和 artifactKey", () => {
    const result = parseControlEventArgsDetailed("show_review_artifact", {
      reason: "没有目标草案。",
    });
    assert.equal(result.success, false);
    if (result.success) return;
    assert.ok(result.error.issues.some((issue) => issue.path.endsWith("artifactId")));
  });

  it("解析 update builder control tools", () => {
    const start = parseControlEventArgs("start_update_builder", {
      summary: "批量重构大纲",
      artifactKey: "outline-builder-1",
      reviewerAgent: "编辑",
      submitForReview: true,
    });
    assert.ok(start);
    assert.equal(start!.type, "start_update_builder");

    const append = parseControlEventArgs("append_update_batch", {
      artifactKey: "outline-builder-1",
      updates: {
        outlineAdjustments: [
          { action: "create", clientKey: "stage-1", title: "第一阶段", kind: "stage" },
          { action: "create", clientKey: "unit-1", parentKey: "stage-1", title: "剧情单元", kind: "plot_unit" },
        ],
      },
    });
    assert.ok(append);
    assert.equal(append!.type, "append_update_batch");

    const text = parseControlEventArgs("put_update_text_block", {
      artifactKey: "outline-builder-1",
      section: "outlineContent",
    });
    assert.ok(text);
    assert.equal(text!.type, "put_update_text_block");

    const itemText = parseControlEventArgs("put_update_item_text_block", {
      artifactKey: "outline-builder-1",
      section: "outlineAdjustments",
      field: "content",
      targetKey: "unit-1",
      summary: "写入章节组详细梗概",
    });
    assert.ok(itemText);
    assert.equal(itemText!.type, "put_update_item_text_block");

    const itemTextBlocks = parseControlEventArgs("put_update_item_text_blocks", {
      artifactKey: "outline-builder-1",
      blocks: [
        {
          section: "outlineAdjustments",
          field: "content",
          targetKey: "unit-1",
          summary: "写入章节组详细梗概",
        },
      ],
    });
    assert.ok(itemTextBlocks);
    assert.equal(itemTextBlocks!.type, "put_update_item_text_blocks");

    const finish = parseControlEventArgs("finish_update_builder", {
      artifactKey: "outline-builder-1",
      summary: "批量大纲草案构建完成",
      reviewerAgent: "编辑",
      submitForReview: true,
    });
    assert.ok(finish);
    assert.equal(finish!.type, "finish_update_builder");
  });

  it("解析 append_outline_tree → AppendOutlineTreeEvent", () => {
    const event = parseControlEventArgs("append_outline_tree", {
      artifactKey: "outline-builder-1",
      summary: "追加第一阶段嵌套大纲树",
      stages: [
        {
          title: "第一阶段 鹿溪镇暗流",
          estimatedWordCount: 120000,
          plotUnits: [
            {
              title: "鹿溪镇的暗流",
              chapterGroups: [
                {
                  title: "裂痕",
                  estimatedWordCount: 30000,
                },
              ],
            },
          ],
        },
      ],
    });

    assert.ok(event);
    assert.equal(event!.type, "append_outline_tree");
    if (event!.type === "append_outline_tree") {
      assert.equal(event.stages[0].plotUnits?.[0].chapterGroups?.[0].title, "裂痕");
    }
  });

  it("append_outline_tree 拒绝 content 字段，避免节点长文本进入 tool arguments", () => {
    const result = parseControlEventArgsDetailed("append_outline_tree", {
      artifactKey: "outline-builder-1",
      stages: [
        {
          title: "第一阶段",
          content: "这里即使很短也不允许，详细内容必须走 block。",
          plotUnits: [
            {
              title: "鹿溪镇的暗流",
              content: "剧情单元摘要也不能放这里。",
              chapterGroups: [
                { title: "裂痕", content: "章节组梗概不能放进 append_outline_tree。" },
              ],
            },
          ],
        },
      ],
    });

    assert.equal(result.success, false);
    if (result.success) return;
    const issueText = result.error.issues.map((issue) => `${issue.path}: ${issue.message}`).join("\n");
    assert.match(issueText, /content/);
    assert.match(issueText, /stages\.0/);
  });

  it("append_outline_tree 拒绝 LLM 手写 parentId/parentKey/clientKey", () => {
    const result = parseControlEventArgsDetailed("append_outline_tree", {
      artifactKey: "outline-builder-1",
      stages: [
        {
          title: "第一阶段",
          clientKey: "stage-1",
          plotUnits: [
            {
              title: "鹿溪镇的暗流",
              parentKey: "stage-1",
              chapterGroups: [
                { title: "裂痕", parentId: "outline-node-1" },
              ],
            },
          ],
        },
      ],
    });

    assert.equal(result.success, false);
    if (result.success) return;
    assert.ok(result.error.issues.some((issue) => issue.path.includes("clientKey")));
    assert.ok(result.error.issues.some((issue) => issue.path.includes("parentKey")));
    assert.ok(result.error.issues.some((issue) => issue.path.includes("parentId")));
  });

  it("append_outline_tree 拒绝空 stages 和空标题", () => {
    const emptyStages = parseControlEventArgsDetailed("append_outline_tree", {
      artifactKey: "outline-builder-1",
      stages: [],
    });
    assert.equal(emptyStages.success, false);
    if (!emptyStages.success) {
      assert.ok(emptyStages.error.issues.some((issue) => issue.path === "stages"));
    }

    const emptyTitle = parseControlEventArgsDetailed("append_outline_tree", {
      artifactKey: "outline-builder-1",
      stages: [{ title: "   " }],
    });
    assert.equal(emptyTitle.success, false);
    if (!emptyTitle.success) {
      assert.ok(emptyTitle.error.issues.some((issue) => issue.path === "stages.0.title"));
    }
  });

  it("append_update_batch allows cross-batch outline parentKey to be completed later", () => {
    const result = parseControlEventArgsDetailed("append_update_batch", {
      artifactKey: "outline-builder-1",
      updates: {
        outlineAdjustments: [
          { action: "create", clientKey: "unit-1", parentKey: "stage-1", title: "剧情单元", kind: "plot_unit" },
        ],
      },
    });

    assert.equal(result.success, true);
  });

  it("append_update_batch rejects long text sections in tool arguments", () => {
    const result = parseControlEventArgsDetailed("append_update_batch", {
      artifactKey: "outline-builder-1",
      updates: {
        outlineContent: "这段长总纲必须走 put_update_text_block",
      },
    });

    assert.equal(result.success, false);
    if (result.success) return;
    assert.ok(result.error.issues.some((issue) => issue.path === "updates.outlineContent"));
  });

  it("append_update_batch rejects overlong item text fields", () => {
    const result = parseControlEventArgsDetailed("append_update_batch", {
      artifactKey: "outline-builder-1",
      updates: {
        outlineAdjustments: [
          {
            action: "create",
            clientKey: "group-1",
            parentKey: "unit-1",
            title: "前三章",
            kind: "chapter_group",
            content: "长".repeat(241),
          },
        ],
      },
    });

    assert.equal(result.success, false);
    if (result.success) return;
    assert.ok(result.error.issues.some((issue) => issue.path === "updates.outlineAdjustments.0.content"));
  });

  it("propose_updates rejects long text sections and overlong item fields", () => {
    const sectionResult = parseControlEventArgsDetailed("propose_updates", {
      summary: "错误提交长总纲",
      updates: {
        outlineContent: "这段长总纲必须走 put_update_text_block",
      },
    });
    assert.equal(sectionResult.success, false);
    if (!sectionResult.success) {
      assert.ok(sectionResult.error.issues.some((issue) => issue.path === "updates.outlineContent"));
    }

    const itemResult = parseControlEventArgsDetailed("propose_updates", {
      summary: "错误提交长章节组梗概",
      updates: {
        outlineAdjustments: [
          {
            action: "create",
            title: "前三章",
            kind: "chapter_group",
            parentKey: "unit-1",
            content: "梗".repeat(241),
          },
        ],
      },
    });
    assert.equal(itemResult.success, false);
    if (!itemResult.success) {
      assert.ok(itemResult.error.issues.some((issue) => issue.path === "updates.outlineAdjustments.0.content"));
    }
  });

  it("put_update_text_block rejects content argument and OpenAI schema does not require it", () => {
    const result = parseControlEventArgsDetailed("put_update_text_block", {
      artifactKey: "outline-builder-1",
      section: "outlineContent",
      content: "正文不能放在工具参数中",
    });

    assert.equal(result.success, false);
    if (!result.success) {
      assert.ok(result.error.issues.some((issue) => issue.message.includes("content")));
    }

    const tool = getOpenAITools(["put_update_text_block"])[0];
    const parameters = tool.function.parameters as {
      properties?: Record<string, unknown>;
      required?: string[];
    };
    assert.equal(parameters.properties?.content, undefined);
    assert.equal(parameters.required?.includes("content"), false);
  });

  it("begin_artifact_output 参数中不接受正文 content", () => {
    const result = parseControlEventArgsDetailed("begin_artifact_output", {
      kind: "outline_draft",
      summary: "前十章大纲修改草案",
      content: "这段正文不应该进入 tool arguments",
    });

    assert.equal(result.success, true);
    if (!result.success) return;
    assert.equal("content" in result.event, false);
  });

  it("解析 submit_beat_plan → BeatPlanProposalEvent", () => {
    const event = parseControlEventArgs("submit_beat_plan", {
      title: "第一章 Beat Plan",
      beatCount: 5,
      summary: "开场→冲突引入→第一次转折→中段高潮→结尾悬念",
      chapterGoal: "让主角进入主线案件",
      sceneBeats: [
        {
          order: 1,
          goal: "发现线索",
          conflict: "线索被对手封锁",
          characters: ["主角"],
          estimatedWords: 1200,
          acceptanceCriteria: "主角必须做出主动选择",
        },
      ],
    });
    assert.ok(event);
    assert.equal(event!.type, "submit_beat_plan");
    if (event!.type === "submit_beat_plan") {
      assert.equal(event!.beatCount, 5);
      assert.equal(event!.chapterGoal, "让主角进入主线案件");
      assert.equal(event!.sceneBeats?.[0]?.goal, "发现线索");
      assert.deepEqual(event!.sceneBeats?.[0]?.characters, ["主角"]);
    }
  });

  it("解析 submit_validation_report → ValidationReportEvent", () => {
    const event = parseControlEventArgs("submit_validation_report", {
      hasConflicts: true,
      conflicts: [
        {
          type: "character",
          summary: "角色「张三」的性格前后矛盾",
          evidence: "第3段写他胆小，第8段写他勇猛",
          suggestion: "统一性格设定或为变化增加铺垫",
        },
      ],
    });
    assert.ok(event);
    assert.equal(event!.type, "submit_validation_report");
    if (event!.type === "submit_validation_report") {
      assert.equal(event!.hasConflicts, true);
      assert.equal(event!.conflicts.length, 1);
    }
  });

  it("解析 submit_evaluation → EvaluationEvent", () => {
    const event = parseControlEventArgs("submit_evaluation", {
      artifactKey: "outline-revision-1",
      verdict: "revise",
      summary: "前 3 章仍缺少小赢节点",
      requiredChanges: "第 2 章需要补一个明确获得线索的小胜利",
      revisionMode: "patch",
      patches: [
        { kind: "text_replace", find: "前天接了个活", replace: "今天接了个活" },
      ],
    });
    assert.ok(event);
    assert.equal(event!.type, "submit_evaluation");
    if (event!.type === "submit_evaluation") {
      assert.equal(event.verdict, "revise");
      assert.equal(event.artifactKey, "outline-revision-1");
      assert.equal(event.revisionMode, "patch");
      assert.equal(event.patches?.[0]?.kind, "text_replace");
    }
  });

  it("解析旧 submit_evaluation revise 参数仍然有效", () => {
    const event = parseControlEventArgs("submit_evaluation", {
      artifactKey: "outline-revision-1",
      verdict: "revise",
      summary: "需要重构这一段。",
    });

    assert.ok(event);
    assert.equal(event!.type, "submit_evaluation");
    if (event!.type === "submit_evaluation") {
      assert.equal(event.revisionMode, undefined);
      assert.equal(event.patches, undefined);
    }
  });

  it("未知 tool name 返回 null", () => {
    const event = parseControlEventArgs("unknown_tool", { foo: "bar" });
    assert.equal(event, null);
  });

  it("非法参数返回 null（评分越界）", () => {
    // hook 评分超过 10
    const event = parseControlEventArgs("submit_quality_report", {
      scores: { hook: 15 },
      qualityGate: "pass",
    });
    assert.equal(event, null);
  });

  it("非法参数返回 null（qualityGate 非法值）", () => {
    const event = parseControlEventArgs("submit_quality_report", {
      scores: { overall: 5 },
      qualityGate: "excellent", // 不是合法值
    });
    assert.equal(event, null);
  });

});

describe("AgentRuntime control tools", () => {
  it("propose_updates can continue to the next model round", async () => {
    const client = createMockClient([
      createToolCallStream("propose_updates", {
        summary: "提交设定草案",
        updates: {
          characters: [{ action: "create", name: "张三", identity: "侠客" }],
        },
      }, "我先提交草案。"),
      createTextStream("草案已提交，等待确认。"),
    ]);
    const runtime = createTestRuntime(client);

    const result = await runtime.runTurn(createRuntimeOptions());

    assert.equal(client.calls, 2);
    assert.equal(result.finishReason, "stop");
    assert.equal(result.controlEvents.length, 1);
    assert.equal(result.controlEvents[0].type, "propose_updates");
    assert.match(result.visibleContent, /我先提交草案。/);
    assert.match(result.visibleContent, /草案已提交，等待确认。/);
  });

  it("does not turn invalid raw tool arguments into empty args", async () => {
    const client = createMockClient([
      createRawToolCallStream(
        "propose_updates",
        "{\"summary\":\"提交大纲草案\",\"updates\":",
        "准备提交草案。"
      ),
      createTextStream("这段内容不应该出现。"),
    ]);
    const runtime = createTestRuntime(client);

    const result = await runtime.runTurn(createRuntimeOptions());

    assert.equal(client.calls, 1);
    assert.equal(result.finishReason, "tool_parse_error");
    assert.equal(result.toolCalls.length, 1);
    assert.equal(result.toolCalls[0].name, "propose_updates");
    assert.equal(result.toolCalls[0].args.__parseError, true);
    assert.equal(result.controlEvents.length, 0);
    assert.match(result.visibleContent, /参数 JSON 解析失败/);
    assert.doesNotMatch(result.visibleContent, /未保存任何变更/);
  });

  it("rejects model tool calls that were not exposed in the current tool list", async () => {
    const client = createMockClient([
      createToolCallStream("start_update_builder", {
        summary: "越权构建大纲草案",
        artifactKey: "outline-builder-unauthorized",
      }, "我准备直接构建大纲草案。"),
      createTextStream("这段内容不应该出现。"),
    ]);
    const runtime = createTestRuntime(client);

    const result = await runtime.runTurn({
      ...createRuntimeOptions(),
      tools: [
        {
          type: "function",
          function: {
            name: "get_novel_info",
            description: "read only",
            parameters: { type: "object", properties: {} },
          },
        },
      ],
    });

    assert.equal(client.calls, 1);
    assert.equal(result.finishReason, "tool_authorization_error");
    assert.equal(result.controlEvents.length, 0);
    assert.match(result.visibleContent, /未向当前 Agent 暴露/);
    assert.match(result.visibleContent, /get_novel_info/);
  });
});

describe("control tool 参数修复提示", () => {
  it("propose_updates 空参会返回字段级 Zod issues 和 TS-like 修复格式", () => {
    const result = parseControlEventArgsDetailed("propose_updates", {});
    assert.equal(result.success, false);
    if (result.success) return;

    assert.equal(result.error.toolName, "propose_updates");
    assert.ok(result.error.issues.some((issue) => issue.path === "summary"));
    assert.ok(result.error.issues.some((issue) => issue.path === "updates"));
    assert.match(result.error.expectedType, /type ProposeUpdatesArgs/);
    assert.match(result.error.expectedType, /summary: string/);
    assert.match(result.error.expectedType, /updates:/);
    assert.match(result.error.minimalExample, /"summary"/);
    assert.match(result.error.minimalExample, /"updates"/);
  });

  it("第一次校验失败会给模型可修复错误", () => {
    const result = parseControlEventArgsDetailed("propose_updates", {});
    assert.equal(result.success, false);
    if (result.success) return;

    const message = formatControlToolValidationMessage(result.error, 1, 2);
    assert.match(message, /第 1\/2 次/);
    assert.match(message, /Zod issues:/);
    assert.match(message, /Expected TypeScript shape:/);
    assert.match(message, /Minimal valid example:/);
    assert.match(message, /正文中说明边界/);
    assert.match(message, /tool arguments 只能放短结构化命令/);
    assert.match(message, /ARTIFACT_OUTPUT_START\/END/);
  });

  it("第二次校验失败会返回硬停止文案，明确未保存任何变更", () => {
    const result = parseControlEventArgsDetailed("propose_updates", {});
    assert.equal(result.success, false);
    if (result.success) return;

    const message = formatControlToolValidationMessage(result.error, 2, 2, true);
    assert.match(message, /连续 2 次校验失败/);
    assert.match(message, /已停止本轮工具循环/);
    assert.match(message, /未保存任何变更/);
  });
});

// ============================================
// 2. AgentRuntimeImpl 结构测试
// ============================================

describe("AgentRuntimeImpl", () => {
  it("可以被实例化", () => {
    const runtime = new AgentRuntimeImpl();
    assert.ok(runtime);
    assert.ok(typeof runtime.runTurn === "function");
  });

  it("实现 AgentRuntime 接口", () => {
    const runtime: AgentRuntime = new AgentRuntimeImpl();
    assert.ok(runtime);
  });

  it("runTurn 返回正确的结构（Mock 模式，AI 未配置）", async () => {
    const runtime = new AgentRuntimeImpl({ isAiConfigured: () => false });

    const options: AgentRuntimeOptions = {
      messages: [
        { role: "system", content: "你是一个测试 Agent。" },
        { role: "user", content: "帮我分析当前章节。" },
      ],
      tools: [],
      toolExecutor: async () => "ok",
      metadata: { callType: "test" },
    };

    const result: AgentTurnResult = await runtime.runTurn(options);

    // 验证返回结构
    assert.equal(typeof result.visibleContent, "string");
    assert.ok(Array.isArray(result.controlEvents));
    assert.ok(Array.isArray(result.toolCalls));
    assert.ok(Array.isArray(result.toolResults));
    // 无工具调用时，controlEvents 应为空
    assert.equal(result.controlEvents.length, 0);
    assert.equal(result.toolCalls.length, 0);
  });

  it("不会把 reasoning_content 回灌到下一轮 messages", async () => {
    const calls: ToolCallTurnOptions[] = [];
    const runtimePort: ModelRuntimePort = {
      streamText: async () => ({ content: "" }),
      completeText: async () => ({ content: "" }),
      completeStructured: (async (schema) => ({ data: schema.parse({}) })) as ModelRuntimePort["completeStructured"],
      runToolCallTurn: async (options) => {
        calls.push(options);
        if (calls.length === 1) {
          return {
            content: "",
            reasoningContent: "很长的内部推理",
            toolCalls: [
              {
                id: "call_get_novel_info",
                type: "function",
                function: {
                  name: "get_novel_info",
                  arguments: "{}",
                },
              },
            ],
            finishReason: "tool_calls",
          };
        }
        return {
          content: "done",
          reasoningContent: "",
          toolCalls: [],
          finishReason: "stop",
        };
      },
    };
    const runtime = new AgentRuntimeImpl({ runtime: runtimePort });

    await runtime.runTurn({
      ...createRuntimeOptions(),
      tools: getOpenAITools(["get_novel_info"]),
      toolExecutor: async () => "read ok",
    });

    assert.equal(calls.length, 2);
    assert.equal(JSON.stringify(calls[1].messages).includes("reasoning_content"), false);
  });

  it("回灌给下一轮模型的长工具结果会截断，但调试记录保留完整结果", async () => {
    const calls: ToolCallTurnOptions[] = [];
    const longResult = "大纲".repeat(4000);
    const runtimePort: ModelRuntimePort = {
      streamText: async () => ({ content: "" }),
      completeText: async () => ({ content: "" }),
      completeStructured: (async (schema) => ({ data: schema.parse({}) })) as ModelRuntimePort["completeStructured"],
      runToolCallTurn: async (options) => {
        calls.push(options);
        if (calls.length === 1) {
          return {
            content: "先查大纲",
            reasoningContent: "",
            toolCalls: [
              {
                id: "call_list_outline_summary",
                type: "function",
                function: {
                  name: "list_outline_summary",
                  arguments: "{}",
                },
              },
            ],
            finishReason: "tool_calls",
          };
        }
        return {
          content: "done",
          reasoningContent: "",
          toolCalls: [],
          finishReason: "stop",
        };
      },
    };
    const runtime = new AgentRuntimeImpl({ runtime: runtimePort });

    const result = await runtime.runTurn({
      ...createRuntimeOptions(),
      tools: getOpenAITools(["list_outline_summary"]),
      toolExecutor: async () => longResult,
    });

    assert.equal(calls.length, 2);
    assert.equal(result.toolResults[0].result, longResult);
    const secondMessages = calls[1].messages as Array<{ role?: string; content?: unknown }>;
    const toolMessage = secondMessages.find((message) => message.role === "tool");
    assert.equal(typeof toolMessage?.content, "string");
    assert.ok((toolMessage!.content as string).length < longResult.length);
    assert.match(toolMessage!.content as string, /工具结果已截断/);
    assert.match(toolMessage!.content as string, /list_outline_summary/);
  });

  it("submit_evaluation 可在同一轮输出报告并终止，不再发起 ACK 后续请求", async () => {
    const evaluationArgs = {
      artifactId: "artifact-1",
      artifactKey: "draft-1",
      verdict: "pass",
      summary: "草案可以提交用户确认。",
    };
    const client = createMockClient([
      createToolCallStream("submit_evaluation", evaluationArgs, "完整审核报告：草案结构成立，可以提交用户确认。"),
    ]);
    const runtime = createTestRuntime(client);

    const result = await runtime.runTurn({
      ...createRuntimeOptions(),
      tools: getOpenAITools(["submit_evaluation"]),
      terminalControlTools: ["submit_evaluation"],
    });

    assert.equal(client.calls, 1);
    assert.equal(result.finishReason, "terminal_control_event");
    assert.match(result.visibleContent, /完整审核报告/);
    assert.equal(result.controlEvents[0]?.type, "submit_evaluation");
  });

  it("submit_evaluation 纯工具调用终止时使用结构化结论生成兜底报告", async () => {
    const client = createMockClient([
      createToolCallStream("submit_evaluation", {
        artifactId: "artifact-1",
        artifactKey: "draft-1",
        verdict: "revise",
        summary: "当前草案需要修改。",
        requiredChanges: "收紧中段节奏并增强章末钩子。",
        revisionMode: "rewrite",
      }),
    ]);
    const runtime = createTestRuntime(client);

    const result = await runtime.runTurn({
      ...createRuntimeOptions(),
      tools: getOpenAITools(["submit_evaluation"]),
      terminalControlTools: ["submit_evaluation"],
    });

    assert.equal(client.calls, 1);
    assert.match(result.visibleContent, /当前草案需要修改/);
    assert.match(result.visibleContent, /需要修改/);
    assert.match(result.visibleContent, /增强章末钩子/);
  });

  it("submit_evaluation 成功后不再执行同轮排在其后的工具", async () => {
    const client = createMockClient([
      createMultiToolCallStream([
        {
          toolName: "submit_evaluation",
          args: {
            artifactId: "artifact-1",
            artifactKey: "draft-1",
            verdict: "pass",
            summary: "审核通过。",
          },
        },
        { toolName: "get_novel_info", args: {} },
      ]),
    ]);
    const runtime = createTestRuntime(client);
    let readCalls = 0;

    const result = await runtime.runTurn({
      ...createRuntimeOptions(),
      tools: getOpenAITools(["submit_evaluation", "get_novel_info"]),
      terminalControlTools: ["submit_evaluation"],
      toolExecutor: async () => {
        readCalls += 1;
        return "read ok";
      },
    });

    assert.equal(client.calls, 1);
    assert.equal(readCalls, 0);
    assert.deepEqual(result.toolCalls.map((call) => call.name), ["submit_evaluation"]);
  });

  it("模型只有 reasoning 且没有正文或工具时返回固定提示，不泄漏 reasoning", async () => {
    const runtimePort: ModelRuntimePort = {
      streamText: async () => ({ content: "" }),
      completeText: async () => ({ content: "" }),
      completeStructured: (async (schema) => ({ data: schema.parse({}) })) as ModelRuntimePort["completeStructured"],
      runToolCallTurn: async () => ({
        content: "",
        reasoningContent: "内部秘密推理内容",
        toolCalls: [],
        finishReason: "stop",
      }),
    };
    const runtime = new AgentRuntimeImpl({ runtime: runtimePort });

    const result = await runtime.runTurn(createRuntimeOptions());

    assert.match(result.visibleContent, /模型未生成可见回复/);
    assert.doesNotMatch(result.visibleContent, /内部秘密推理内容/);
  });

  it("executes safe read tool calls in parallel", async () => {
    const client = createMockClient([
      createMultiToolCallStream([
        { toolName: "get_novel_info", args: {} },
        { toolName: "list_outline_summary", args: {} },
      ], "checking context"),
      createTextStream("done"),
    ]);
    const runtime = createTestRuntime(client);

    let releaseFirstTool!: () => void;
    let resolveFirstStarted!: () => void;
    const firstStarted = new Promise<void>((resolve) => {
      resolveFirstStarted = resolve;
    });
    const firstCanFinish = new Promise<void>((resolve) => {
      releaseFirstTool = resolve;
    });
    const startedTools: string[] = [];

    const runPromise = runtime.runTurn({
      ...createRuntimeOptions(),
      toolExecutor: async (toolName) => {
        startedTools.push(toolName);
        if (toolName === "get_novel_info") {
          resolveFirstStarted();
          await firstCanFinish;
        }
        return `result from ${toolName}`;
      },
    });

    await firstStarted;
    assert.deepEqual(startedTools, ["get_novel_info", "list_outline_summary"]);

    releaseFirstTool();
    const result = await runPromise;

    assert.deepEqual(startedTools, ["get_novel_info", "list_outline_summary"]);
    assert.equal(result.visibleContent, "checking context\n\ndone");
  });

  it("limits parallel safe tool calls to five per batch", async () => {
    const toolCalls = Array.from({ length: 6 }, () => ({ toolName: "get_novel_info", args: {} }));
    const client = createMockClient([
      createMultiToolCallStream(toolCalls, "checking context"),
      createTextStream("done"),
    ]);
    const runtime = createTestRuntime(client);
    let active = 0;
    let maxActive = 0;

    const result = await runtime.runTurn({
      ...createRuntimeOptions(),
      toolExecutor: async () => {
        active += 1;
        maxActive = Math.max(maxActive, active);
        await new Promise((resolve) => setTimeout(resolve, 5));
        active -= 1;
        return "ok";
      },
    });

    assert.equal(maxActive, 5);
    assert.equal(result.toolResults.length, 6);
    assert.equal(result.visibleContent, "checking context\n\ndone");
  });

  it("emits tool result callbacks after read tools complete", async () => {
    const client = createMockClient([
      createToolCallStream("get_novel_info", {}, "checking context"),
      createTextStream("done"),
    ]);
    const runtime = createTestRuntime(client);
    const toolResults: Array<{ toolName: string; result: string }> = [];

    const result = await runtime.runTurn({
      ...createRuntimeOptions(),
      toolExecutor: async () => JSON.stringify({ novelName: "遗产猎人", chapterTitle: "第一章" }),
      onToolResult: (toolName, _args, toolResult) => {
        toolResults.push({ toolName, result: toolResult });
      },
    });

    assert.deepEqual(toolResults, [
      { toolName: "get_novel_info", result: JSON.stringify({ novelName: "遗产猎人", chapterTitle: "第一章" }) },
    ]);
    assert.equal(result.visibleContent, "checking context\n\ndone");
  });
});

describe("AgentRuntimeImpl LangSmith tracing", () => {
  it("wraps read tool execution in LangSmith tool traces without changing output", async () => {
    await withEnabledLangSmithForTest(async () => {
      const traceCalls: Array<{ name: string; metadata: Record<string, unknown> }> = [];
      __setLangSmithTraceRunnerForTests(async (name, metadata, fn) => {
        traceCalls.push({ name, metadata });
        return fn();
      });

      const client = createMockClient([
        createToolCallStream("get_character_detail", { characterId: "char-1" }, "before tool"),
        createTextStream("after tool"),
      ]);
      const runtime = createTestRuntime(client);

      const result = await runtime.runTurn({
        ...createRuntimeOptions(),
        metadata: {
          callType: "test-tool-trace",
          agentId: "写作",
          taskId: "task-1",
          novelId: "novel-1",
          userId: "user-1",
        },
        toolExecutor: async (toolName) => `result from ${toolName}`,
      });

      assert.equal(result.toolResults[0].result, "result from get_character_detail");
      assert.equal(result.visibleContent, "before tool\n\nafter tool");
      const toolTrace = traceCalls.find((call) => call.name === "tool:get_character_detail");
      assert.ok(toolTrace);
      assert.equal(toolTrace.metadata.agentId, "写作");
      assert.equal(toolTrace.metadata.taskId, "task-1");
      assert.equal(toolTrace.metadata.novelId, "novel-1");
      assert.equal(toolTrace.metadata.userId, "user-1");
      assert.equal(toolTrace.metadata.toolKind, "read");
    });
  });
});
