/**
 * Control Tools 定义（Phase 0：协议落地）
 *
 * @module agents/tools/control/control-tools
 * @description Agent 控制面工具：质量评分、更新提案、Beat Plan、校验报告、草案评审。
 *   替代 JSON 信封中的 wantsToCall / scores / qualityGate / updates / conflicts 字段。
 *
 *   这些工具的特点：
 *   - toolKind: "control" — runtime 会拦截并转为 AgentControlEvent
 *   - 参数短小、结构化 — 不承载长篇正文
 *   - 不直接写库 — 由 control-event-processor 或 service 处理
 *   - 执行器返回简单确认 — 实际业务逻辑在 runtime / operationWorkflow 中
 *
 * @phase Phase 0 — 协议和接口落地
 */

import { registerTool } from "../registry";
import { controlToolPermission } from "../permissions";
import type { ToolCapability } from "../permissions";
import {
  QualityReportToolArgsSchema,
  ProposalUpdatesToolArgsSchema,
  StartUpdateBuilderToolArgsSchema,
  AppendUpdateBatchToolArgsSchema,
  AppendOutlineTreeToolArgsSchema,
  PutUpdateTextBlockToolArgsSchema,
  PutUpdateItemTextBlockToolArgsSchema,
  PutUpdateItemTextBlocksToolArgsSchema,
  FinishUpdateBuilderToolArgsSchema,
  BeginArtifactOutputToolArgsSchema,
  ShowReviewArtifactToolArgsSchema,
  BeatPlanProposalToolArgsSchema,
  ValidationReportToolArgsSchema,
  EvaluationToolArgsSchema,
} from "@/shared/contracts/agent-control";
import {
  AGENT_UPDATE_CHANNEL_RULES_PROMPT,
  ITEM_TEXT_BLOCK_TOOLS_CN_TEXT,
  TEXT_UPDATE_SECTIONS_TEXT,
  TOOL_SHORT_TEXT_MAX,
  UPDATE_BUILDER_TOOL_CHAIN_TEXT,
} from "@/shared/contracts/agent-update-channels";

// ============================================
// 注册所有 control tools
// ============================================

registerTool(
  {
    name: "submit_evaluation",
    description:
      "提交通用评估结论，用于 evaluator/reviser 循环。适用于编辑或校验对其他 Agent 产物进行复审时，表达 pass、revise 或 block。" +
      "必须尽量引用 artifactId；长篇评审报告保留在正文文本中；此工具只提交结构化结论和必要修改摘要。",
    inputSchema: EvaluationToolArgsSchema,
    permission: controlToolPermission("control.evaluation", ["编辑", "校验"]),
    toolKind: "control",
  },
  async (args) => {
    const a = args as { artifactKey: string; verdict: string };
    return JSON.stringify({
      acknowledged: true,
      artifactKey: a.artifactKey,
      verdict: a.verdict,
    });
  }
);

registerTool(
  {
    name: "submit_quality_report",
    description:
      "提交编辑评审或校验的质量评分报告。" +
      "在你完成对正文的审阅后，用此工具提交结构化评分。" +
      "评分维度：hook（开篇吸引力）、tension（张力）、payoff（回报感）、" +
      "pacing（节奏）、endingHook（结尾悬念）、readerPromise（读者期待）、overall（总体）。" +
      "qualityGate 决定下一步：pass（通过）、revise（小修）、rewrite（重写）。" +
      "长篇评审报告请保留在正文文本中，不要放入此工具的参数。",
    inputSchema: QualityReportToolArgsSchema,
    permission: controlToolPermission("control.quality"),
    toolKind: "control",
  },
  async (args) => {
    const a = args as { qualityGate: string; scores?: { overall?: number } };
    return JSON.stringify({
      acknowledged: true,
      qualityGate: a.qualityGate,
      overallScore: a.scores?.overall ?? "N/A",
    });
  }
);

registerTool(
  {
    name: "propose_updates",
    description:
      "向用户提议短小的设定/大纲/参考资料修改，并在参数中提交短结构化变更数据。" +
      "当你需要新增、修改、删除角色/地点/物品/势力/术语/角色经历/大纲状态/短小大纲修补/伏笔/参考资料时，调用此工具。" +
      "系统会先创建待审核草案 ReviewArtifact；只有用户最终确认应用后，才会保存到正式数据库。" +
      "如果用户要求先由其他 Agent 审核、写入前审核、改到满意再写入，请提供 artifactKey，并设置 reviewerAgent。" +
      "" +
      "重要：" + AGENT_UPDATE_CHANNEL_RULES_PROMPT +
      "注意：tool arguments 本身必须是合法 JSON；summary、updates 等字符串字段里的中文正文引用不要使用半角英文双引号 \"，请改用中文引号「」或书名号《》。如果必须使用半角英文双引号，必须写成转义形式 \\\"，否则会导致工具参数 JSON 解析失败。" +
      "- updates.characters: 角色变更列表 [{ action: 'create'|'update'|'delete', name: '...', ... }]" +
      "- updates.locations: 地点变更列表" +
      "- updates.items: 物品变更列表" +
      "- updates.factions: 势力变更列表" +
      "- updates.glossaries: 术语变更列表" +
      "- updates.characterExperiences: 角色经历变更列表" +
      "- updates.outline: 大纲状态更新 [{ nodeId: '...', status: 'planned'|... }]" +
      `- updates.outlineAdjustments: 短小大纲结构调整。创建节点必须提供 kind 和 title/nodeTitle；content 只能是 ${TOOL_SHORT_TEXT_MAX} 字以内摘要；长章节组梗概必须走 update builder + ${ITEM_TEXT_BLOCK_TOOLS_CN_TEXT}。` +
      "- updates.foreshadowing: 伏笔变更" +
      "- updates.references: 参考资料变更" +
      "" +
      `禁止在本工具 updates 中提供 ${TEXT_UPDATE_SECTIONS_TEXT}。` +
      `角色/地点/物品/势力描述、角色经历、伏笔说明、参考资料 content 都只能写短摘要；长文本使用 ${UPDATE_BUILDER_TOOL_CHAIN_TEXT}。` +
      "每个变更项必须包含 action 字段（create/update/delete/payoff/abandon），以及对应类型的必填字段。" +
      "不要把长篇正文放进 updates 参数；你的变更分析说明保留在正文中。",
    inputSchema: ProposalUpdatesToolArgsSchema,
    permission: controlToolPermission("control.proposal"),
    toolKind: "control",
  },
  async (args) => {
    const a = args as { summary: string; updates?: Record<string, unknown> };
    const sectionNames = a.updates ? Object.keys(a.updates).filter((k) => {
      const v = a.updates![k];
      return Array.isArray(v) ? v.length > 0 : Boolean(v);
    }) : [];
    return JSON.stringify({
      acknowledged: true,
      summary: a.summary,
      sections: sectionNames.length,
      sectionNames,
    });
  }
);

registerTool(
  {
    name: "start_update_builder",
    description:
      "开始或打开一个批量更新草稿箱，用于大纲重构、批量设定、带格式内容等不适合一次性塞进 propose_updates 的任务。" +
      `只提交 summary、artifactKey、reviewerAgent 等短元数据；后续用 ${UPDATE_BUILDER_TOOL_CHAIN_TEXT} 分批填充。` +
      "同一批构建的所有工具调用必须使用同一个 artifactKey。",
    inputSchema: StartUpdateBuilderToolArgsSchema,
    permission: controlToolPermission("control.builder"),
    toolKind: "control",
  },
  async (args) => {
    const a = args as { artifactKey: string; summary: string };
    return JSON.stringify({ acknowledged: true, artifactKey: a.artifactKey, summary: a.summary });
  }
);

registerTool(
  {
    name: "append_update_batch",
    description:
      "向批量更新草稿箱追加一批短小结构化变更。一次可以提交多个 section、多条 item。" +
      "适合 characters、locations、items、factions、glossaries、characterExperiences、outline、outlineAdjustments、foreshadowing、references。" +
      "注意：复杂大纲创建、展开、重构、迁移必须优先使用 append_outline_tree，不要手写整棵 outlineAdjustments 树。" +
      "outlineAdjustments 仅用于短小修补、已有节点更新或兼容旧流程；如果确实手写新节点，parentKey 可以引用之前批次里的 clientKey，最终严格校验发生在 finish_update_builder。" +
      `禁止提交 ${TEXT_UPDATE_SECTIONS_TEXT}；这些长文本 section 必须用 put_update_text_block。` +
      `所有数组 item 文本字段只能写短摘要，outlineAdjustments[].content 不得超过 ${TOOL_SHORT_TEXT_MAX} 字；长章节组梗概、角色长背景、伏笔长说明等先用本工具创建/定位 item，再用 ${ITEM_TEXT_BLOCK_TOOLS_CN_TEXT} 写入。`,
    inputSchema: AppendUpdateBatchToolArgsSchema,
    permission: controlToolPermission("control.builder"),
    toolKind: "control",
  },
  async (args) => {
    const a = args as { artifactKey: string; updates?: Record<string, unknown> };
    return JSON.stringify({
      acknowledged: true,
      artifactKey: a.artifactKey,
      sectionNames: a.updates ? Object.keys(a.updates) : [],
    });
  }
);

registerTool(
  {
    name: "append_outline_tree",
    description:
      "向批量更新草稿箱追加一批嵌套结构化大纲树。用于大纲创建、展开、重构、迁移等复杂结构任务。" +
      "输入只写 stage → plotUnits → chapterGroups 的自然树；不要提供 parentId、parentKey 或 clientKey，服务端会自动展开为合法 outlineAdjustments。" +
      "每个节点只允许 title 和可选 estimatedWordCount；不要提供 content 字段，不要写整章梗概、正文、长段落或对白。" +
      `长总纲文本使用 put_update_text_block(section=outlineContent)；节点详细梗概在树追加后用 ${ITEM_TEXT_BLOCK_TOOLS_CN_TEXT} 写入。追加完成后调用 finish_update_builder。`,
    inputSchema: AppendOutlineTreeToolArgsSchema,
    permission: controlToolPermission("control.builder", ["剧情"]),
    toolKind: "control",
  },
  async (args) => {
    const a = args as { artifactKey: string; stages?: unknown[] };
    return JSON.stringify({
      acknowledged: true,
      artifactKey: a.artifactKey,
      stageCount: a.stages?.length ?? 0,
    });
  }
);

registerTool(
  {
    name: "put_update_text_block",
    description:
      `向批量更新草稿箱写入一个长文本 section，只支持 ${TEXT_UPDATE_SECTIONS_TEXT}。` +
      "工具参数只放 artifactKey、section、summary；不要在参数里放正文 content。" +
      "长文本必须写在本轮 assistant 正文的 ARTIFACT_OUTPUT_START 和 ARTIFACT_OUTPUT_END 标记之间，服务端会从标记块读取。" +
      "后续调用 finish_update_builder 才会做最终校验和提交。",
    inputSchema: PutUpdateTextBlockToolArgsSchema,
    permission: controlToolPermission("control.builder"),
    toolKind: "control",
  },
  async (args) => {
    const a = args as { artifactKey: string; section: string };
    return JSON.stringify({ acknowledged: true, artifactKey: a.artifactKey, section: a.section });
  }
);

registerTool(
  {
    name: "put_update_item_text_block",
    description:
      "向批量更新草稿箱的某个数组 item 写入长文本字段。" +
      "适合 outlineAdjustments.content 的章节组长梗概、角色长背景、地点/物品/势力长描述、角色经历长内容、伏笔长说明、参考资料长内容等。" +
      "调用前必须先用 append_update_batch 或 append_outline_tree 创建/追加目标 item；本工具参数只放 artifactKey、section、field、targetId/targetKey/targetName、summary 等短元数据。" +
      "长文本必须写在本轮 assistant 正文的 ARTIFACT_OUTPUT_START 和 ARTIFACT_OUTPUT_END 标记之间，服务端会按工具调用顺序读取对应标记块。" +
      "如果找不到目标 item、字段不允许或缺少标记块，系统会发送 update_builder_text_ignored，不会静默保存。",
    inputSchema: PutUpdateItemTextBlockToolArgsSchema,
    permission: controlToolPermission("control.builder"),
    toolKind: "control",
  },
  async (args) => {
    const a = args as { artifactKey: string; section: string; field: string };
    return JSON.stringify({ acknowledged: true, artifactKey: a.artifactKey, section: a.section, field: a.field });
  }
);

registerTool(
  {
    name: "put_update_item_text_blocks",
    description:
      "批量向更新草稿箱的多个数组 item 写入长文本字段，作用等同于多次 put_update_item_text_block，但只消耗一次工具调用。" +
      "blocks 数组只放 section、field、targetId/targetKey/targetName、summary 等短元数据；不要放正文 content。" +
      "本轮 assistant 正文必须按 blocks 顺序提供同样数量的 ARTIFACT_OUTPUT_START/END 标记块。" +
      "适合一次写入多个角色背景、多个章节组梗概、多个地点/势力描述，避免工具循环轮次耗尽。",
    inputSchema: PutUpdateItemTextBlocksToolArgsSchema,
    permission: controlToolPermission("control.builder"),
    toolKind: "control",
  },
  async (args) => {
    const a = args as { artifactKey: string; blocks?: unknown[] };
    return JSON.stringify({ acknowledged: true, artifactKey: a.artifactKey, blockCount: a.blocks?.length ?? 0 });
  }
);

registerTool(
  {
    name: "finish_update_builder",
    description:
      "完成批量更新草稿箱构建。系统会把同一 artifactKey 下已追加的内容合并为 agent_updates 草案，执行严格校验。" +
      "如果提供 reviewerAgent 或 submitForReview=true，校验通过后进入 Agent 复审；校验失败则保持 draft 并返回错误事件，不进入复审。",
    inputSchema: FinishUpdateBuilderToolArgsSchema,
    permission: controlToolPermission("control.builder"),
    toolKind: "control",
  },
  async (args) => {
    const a = args as { artifactKey: string; summary: string };
    return JSON.stringify({ acknowledged: true, artifactKey: a.artifactKey, summary: a.summary });
  }
);

registerTool(
  {
    name: "begin_artifact_output",
    description:
      "声明本轮 assistant 正文是一份需要进入 ReviewArtifact 的长文本产物。" +
      "适用于纯文本大纲草稿、章节正文草案、设定草案、返工说明和 Beat Plan 正文。" +
      "结构化大纲的创建、修改、展开、重构、迁移必须使用 agent_updates 草案：短小变更用 propose_updates，批量节点树或长总纲用 update builder；不要使用本工具替代结构化节点树。" +
      "此工具参数只放 kind、summary、artifactKey、reviewerAgent 等短元数据；不要把草案正文放入参数。" +
      "调用此工具时，待审核正文必须放在 ARTIFACT_OUTPUT_START 和 ARTIFACT_OUTPUT_END 标记块中，系统只保存标记块里的内容。",
    inputSchema: BeginArtifactOutputToolArgsSchema,
    permission: controlToolPermission("control.artifact", ["设定", "剧情", "写作"]),
    toolKind: "control",
  },
  async (args) => {
    const a = args as { kind: string; summary: string; artifactKey?: string };
    return JSON.stringify({
      acknowledged: true,
      kind: a.kind,
      artifactKey: a.artifactKey,
      summary: a.summary,
    });
  }
);

registerTool(
  {
    name: "show_review_artifact",
    description:
      "请求前端展示一个已经存在的 ReviewArtifact 草案。你只能提供 artifactId 或 artifactKey，以及简短原因；" +
      "服务端会校验草案属于当前小说后再发送展示事件。此工具不会应用、修改或删除草案。",
    inputSchema: ShowReviewArtifactToolArgsSchema,
    permission: controlToolPermission("control.artifact"),
    toolKind: "control",
  },
  async (args) => {
    const a = args as { artifactId?: string; artifactKey?: string; reason?: string };
    return JSON.stringify({
      acknowledged: true,
      artifactId: a.artifactId ?? null,
      artifactKey: a.artifactKey ?? null,
      reason: a.reason ?? null,
    });
  }
);

registerTool(
  {
    name: "submit_beat_plan",
    description:
      "提交 Beat Plan（节拍计划）提案。" +
      "Beat Plan 是剧情顾问为章节规划的结构化节拍序列，包含每个节拍的核心事件、情感变化和字数分配。" +
      "具体的节拍内容和取舍分析请保留在正文文本中。",
    inputSchema: BeatPlanProposalToolArgsSchema,
    permission: controlToolPermission("control.beat"),
    toolKind: "control",
  },
  async (args) => {
    return JSON.stringify({
      acknowledged: true,
      title: args.title,
      beatCount: args.beatCount,
    });
  }
);

registerTool(
  {
    name: "submit_validation_report",
    description:
      "提交校验报告的结构化冲突列表。" +
      "在你完成对正文的一致性校验后，用此工具提交发现的冲突。" +
      "冲突类型：character（角色）、setting（设定）、plot（剧情）、logic（逻辑）、world（世界观）。" +
      "长篇校验报告（包括冲突的详细分析、文本引用、上下文解释）请保留在正文文本中，不要放入此工具的参数。" +
      "如果未发现冲突（hasConflicts=false），仍可提交空 conflicts 数组以表示校验已完成。",
    inputSchema: ValidationReportToolArgsSchema,
    permission: controlToolPermission("control.validation"),
    toolKind: "control",
  },
  async (args) => {
    const a = args as { hasConflicts: boolean; conflicts?: unknown[] };
    return JSON.stringify({
      acknowledged: true,
      hasConflicts: a.hasConflicts,
      conflictCount: a.conflicts?.length ?? 0,
    });
  }
);
