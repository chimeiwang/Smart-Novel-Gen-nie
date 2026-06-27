#!/usr/bin/env tsx

/**
 * 生成 LangGraph Studio 可直接运行的完整 GraphState 输入。
 *
 * 用法：
 *   npm run studio:input -- \
 *     --novel-id <novelId> \
 *     --chapter-id <chapterId> \
 *     --user-id <userId> \
 *     --message "继续写本章"
 */

import { prisma } from "@/shared/db/prisma";
import { aggregateNovelContextLightweight } from "@/shared/lib/context-aggregator";
import { CORE_AGENT_IDS } from "@/agents/graph/state";
import type { GraphState } from "@/agents/graph/graph-definition";

type CliArgs = Record<string, string>;

function parseArgs(argv: string[]): CliArgs {
  const args: CliArgs = {};
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) continue;
    const key = token.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) {
      args[key] = "true";
      continue;
    }
    args[key] = next;
    i += 1;
  }
  return args;
}

function requireArg(args: CliArgs, name: string): string {
  const value = args[name];
  if (!value) {
    throw new Error(`缺少参数 --${name}`);
  }
  return value;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const novelId = requireArg(args, "novel-id");
  const chapterId = requireArg(args, "chapter-id");
  const userId = requireArg(args, "user-id");
  const userMessage = args.message ?? "请基于当前章节上下文给出下一步建议。";
  const targetWordCount = Number(args["target-word-count"] ?? 1200);

  const novel = await prisma.novel.findUnique({
    where: { id: novelId },
    select: { id: true, userId: true },
  });
  if (!novel) {
    throw new Error(`Novel not found: ${novelId}`);
  }
  if (novel.userId && novel.userId !== userId) {
    throw new Error("userId 与小说归属不匹配");
  }

  const aggregatedNovelData = await aggregateNovelContextLightweight(novelId, chapterId);
  const novelData: GraphState["novelData"] = {
    ...aggregatedNovelData,
    novelId,
    chapterId,
  };
  const task = await prisma.writingTask.create({
    data: {
      novelId,
      chapterId,
      targetWordCount,
      selectedAgents: CORE_AGENT_IDS.join(","),
      phase: "active",
      conversationHistory: "[]",
    },
  });

  const state: GraphState = {
    taskId: task.id,
    userId,
    novelId,
    chapterId,
    targetWordCount,
    phase: "active",
    userMessage,
    pendingUserResponse: false,
    conversationHistory: [],
    activeAgent: null,
    currentOperation: null,
    operationMode: "operation_graph",
    operationStage: null,
    loreAdvisorOutput: null,
    plotAdvisorOutput: null,
    writerOutput: null,
    validatorOutput: null,
    editorOutput: null,
    generatedContent: "",
    pendingUpdates: null,
    novelData,
    pendingAgentCall: null,
    errorMessage: null,
    streamCallbacks: {},
    eventCallbacks: undefined,
    qualityCheckId: null,
    controlEvents: undefined,
    activeArtifactId: null,
    artifactMode: "none",
    reviewerAgent: null,
    reviserAgent: null,
    pendingArtifactRevision: null,
    artifactIteration: 0,
    maxArtifactIterations: 5,
  };

  console.log(JSON.stringify(state, null, 2));
  console.error(`\n已创建 Studio 调试 WritingTask: ${task.id}`);
}

main()
  .catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
