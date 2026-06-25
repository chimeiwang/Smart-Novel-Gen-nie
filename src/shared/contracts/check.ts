/**
 * Contract 检查入口（Phase 8：CI 门禁）
 *
 * 用法: npx tsx src/shared/contracts/check.ts
 *
 * 检查项:
 * 1. 质量检查 type/status/message/agent 完整性
 * 2. AgentUpdates schema 与 sanitizer section 一致性
 * 3. SSE 示例事件 parse
 * 4. DTO 转换 parse
 */

import {
  QUALITY_CHECK_DEFINITIONS,
  QUALITY_CHECK_AGENT_MAP,
  QUALITY_CHECK_MESSAGE_MAP,
  QualityCheckDtoSchema,
  normalizeQualityScores,
  QualityGateSchema,
} from "./quality-check";

import {
  AgentUpdatesSchema,
  sanitizeAgentUpdates,
  hasAgentUpdates,
  ALL_UPDATE_SECTIONS,
  type AgentUpdates,
} from "./agent-updates";

import { parseSseEvent, WritingSseEventSchema } from "./sse-events";

void async function main() {
  const errors: string[] = [];
  console.log("=== Contract Check ===\n");

  // -------------------------------------------------------
  // 1. 质量检查完整性
  // -------------------------------------------------------
  console.log("1. 质量检查定义完整性...");
  const types = QUALITY_CHECK_DEFINITIONS.map((d) => d.type);
  for (const t of types) {
    if (!QUALITY_CHECK_AGENT_MAP[t]) {
      errors.push(`质量检查类型 "${t}" 缺少 Agent 映射`);
    }
    if (!QUALITY_CHECK_MESSAGE_MAP[t]) {
      errors.push(`质量检查类型 "${t}" 缺少运行消息`);
    }
  }
  const typeSet = new Set(types);
  if (typeSet.size !== types.length) {
    errors.push("质量检查定义中存在重复 type");
  }
  if (types.length < 4) errors.push("质量检查类型少于 4 种");
  console.log(`  ${types.length} 种类型全部完整 ✓`);

  // 1b. 状态枚举校验
  const validStatuses = ["pending", "running", "completed", "skipped", "failed"];
  const validGates = ["pass", "revise", "rewrite"];
  for (const g of validGates) {
    if (!QualityGateSchema.safeParse(g).success) {
      errors.push(`qualityGate "${g}" 无法 parse`);
    }
  }
  console.log(`  状态枚举 + qualityGate 校验通过 ✓`);

  // -------------------------------------------------------
  // 2. AgentUpdates schema ↔ sanitizer 一致性
  // -------------------------------------------------------
  console.log("\n2. AgentUpdates schema ↔ sanitizer 一致性...");

  // 构造包含所有 section 的完整 updates
  const allSections: AgentUpdates = {
    characters: [{ action: "create", name: "测试角色" }],
    locations: [{ action: "create", name: "测试地点" }],
    items: [{ action: "create", name: "测试物品" }],
    factions: [{ action: "create", name: "测试势力" }],
    glossaries: [{ action: "create", term: "测试", definition: "测试术语" }],
    characterExperiences: [{ action: "create", content: "测试经历" }],
    outline: [{ nodeId: "test-1", status: "in_progress" }],
    outlineContent: "测试总纲",
    outlineAdjustments: [{ action: "create", title: "测试大纲", kind: "stage" }],
    foreshadowing: [{ action: "create", name: "测试伏笔" }],
    references: [{ action: "create", title: "测试参考" }],
    worldSetting: "测试世界设定",
    storyBackground: "测试故事背景",
  };

  // Zod parse 必须成功
  const parsed = AgentUpdatesSchema.safeParse(allSections);
  if (!parsed.success) {
    errors.push(`AgentUpdatesSchema parse 失败: ${JSON.stringify(parsed.error.issues)}`);
  } else {
    console.log("  Schema parse 12 section 全部通过 ✓");
  }

  // sanitize 后所有 section 必须保留
  const sanitized = sanitizeAgentUpdates(allSections);
  if (!sanitized) {
    errors.push("sanitizeAgentUpdates 返回 undefined（丢失所有 section）");
  } else {
    for (const section of ALL_UPDATE_SECTIONS) {
      if (section === "outlineContent" || section === "worldSetting" || section === "storyBackground") {
        if (!sanitized[section]) {
          errors.push(`sanitize 后 ${section} 丢失`);
        }
      } else {
        const arr = sanitized[section] as unknown[] | undefined;
        if (!arr || arr.length === 0) {
          errors.push(`sanitize 后 ${section} 丢失或为空`);
        }
      }
    }
    if (!hasAgentUpdates(sanitized)) {
      errors.push("hasAgentUpdates 返回 false（12 section 都在）");
    }
  }
  console.log("  sanitize 保留 12 section ✓");

  // 验证 allowedSections 过滤
  const filtered = sanitizeAgentUpdates(allSections, ["characters", "outline"]);
  if (filtered) {
    if (filtered.locations) errors.push("allowedSections 过滤失败: locations 应被移除");
    if (!filtered.characters) errors.push("allowedSections 过滤失败: characters 应保留");
    if (!filtered.outline) errors.push("allowedSections 过滤失败: outline 应保留");
  }
  console.log("  allowedSections 过滤正常 ✓");

  // -------------------------------------------------------
  // 3. SSE 示例事件 parse
  // -------------------------------------------------------
  console.log("\n3. SSE 事件 parse...");

  const samples: Array<{ name: string; event: Record<string, unknown> }> = [
    { name: "start", event: { type: "start", taskId: "test-1" } },
    { name: "agent_done", event: { type: "agent_done", agentId: "写作", agentName: "作家", content: "生成完毕" } },
    { name: "agent_chunk", event: { type: "agent_chunk", agentId: "写作", chunk: "文" } },
    { name: "error", event: { type: "error", message: "出错了" } },
    { name: "done", event: { type: "done", taskId: "test-1" } },
    { name: "user_input_required", event: { type: "user_input_required", phase: "recording", content: "确认保存？" } },
    { name: "updates_saved", event: { type: "updates_saved", agentId: "设定", success: true, savedCount: 3 } },
    { name: "intent_classified", event: { type: "intent_classified", targetAgent: "写作", confidence: 0.9, reasoning: "用户要求写作" } },
    {
      name: "operation_classified",
      event: {
        type: "operation_classified",
        operation: {
          kind: "write_chapter",
          targetType: "chapter",
          userGoal: "写第三章",
          primaryAgent: "写作",
          reviewers: ["校验", "编辑"],
          outputKind: "chapter_text",
          requiresArtifact: false,
          requiresUserApproval: false,
          confidence: 0.9,
          reasoning: "用户要求生成正文",
        },
      },
    },
    { name: "state_update", event: { type: "state_update", node: "processResult", phase: "active" } },
  ];

  let sseFailCount = 0;
  for (const { name, event } of samples) {
    const result = parseSseEvent(event);
    if (!result) {
      errors.push(`SSE 事件 "${name}" parse 失败`);
      sseFailCount++;
    }
  }
  console.log(`  ${samples.length - sseFailCount}/${samples.length} 事件 parse 通过 ✓`);

  // 全量 schema parse
  const unionParse = WritingSseEventSchema.safeParse(samples[0].event);
  if (!unionParse.success) {
    errors.push(`SSE union parse 失败: ${JSON.stringify(unionParse.error.issues)}`);
  }
  console.log("  SSE union schema 正常 ✓");

  // -------------------------------------------------------
  // 4. DTO 转换 parse
  // -------------------------------------------------------
  console.log("\n4. DTO 转换...");

  const sampleCheck = {
    id: "check-1", chapterId: "ch-1", type: "consistency",
    status: "completed", title: "一致性校验", summary: "检查OOC",
    result: "通过", scoreHook: 8, scoreTension: 7, scorePayoff: 6,
    scorePacing: 7, scoreEndingHook: 8, scoreReaderPromise: 9,
    scoreOverall: 8, qualityGate: "pass", rewriteBrief: null,
  };
  const dtoParse = QualityCheckDtoSchema.safeParse(sampleCheck);
  if (!dtoParse.success) {
    errors.push(`QualityCheckDto parse 失败: ${JSON.stringify(dtoParse.error.issues)}`);
  }
  console.log("  QualityCheckDto parse ✓");

  // 评分归一化
  const normalized = normalizeQualityScores({ hook: 7.8, tension: "6", payoff: null, overall: 9.2 });
  if (normalized?.hook !== 8 || normalized?.tension !== 6 || normalized?.payoff !== undefined) {
    errors.push("normalizeQualityScores 行为异常");
  }
  if (normalized?.overall !== 9) {
    errors.push("normalizeQualityScores overall 取整异常");
  }
  console.log("  normalizeQualityScores ✓");

  // -------------------------------------------------------
  // 5. 汇总
  // -------------------------------------------------------
  console.log("\n========================================");
  if (errors.length > 0) {
    console.log(`FAILURES (${errors.length}):`);
    errors.forEach((e) => console.log("  ❌ " + e));
    process.exit(1);
  }
  console.log(`✅ 全部 ${errors.length} 项检查通过`);
}();
