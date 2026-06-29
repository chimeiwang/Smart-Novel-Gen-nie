/**
 * 共享上下文构建器
 *
 * @module agents/graph/context-builder
 * @description 所有 Agent 节点共享的上下文构建函数。v5.2 引入分层策略。
 *
 * ## 两种模式
 * - buildContextIndex() — ~200 token 索引，供工具调用型 Agent 使用
 * - buildNovelContext() — ~5000 token 完整上下文，供生成型 Agent 使用
 */

import { getActiveArtifactId, type CoreAgentId, type WritingState } from "./state";

/** 控制哪些上下文段需要构建 */
export interface ContextBuildOptions {
  /** 是否包含世界设定 */
  worldSetting?: boolean;
  /** 是否包含故事背景 */
  storyBackground?: boolean;
  /** 是否包含作品圣经 */
  writingBible?: boolean;
  /** 是否包含故事进展 */
  storyProgress?: boolean;
  /** 是否包含剧情进度 */
  plotProgress?: boolean;
  /** 是否包含角色设定 */
  characters?: boolean;
  /** 是否包含势力设定 */
  factions?: boolean;
  /** 是否包含地点设定 */
  locations?: boolean;
  /** 是否包含物品设定 */
  items?: boolean;
  /** 是否包含术语表 */
  glossaries?: boolean;
  /** 是否包含大纲 */
  outline?: boolean;
  /** 是否包含伏笔 */
  foreshadowings?: boolean;
  /** 是否包含参考资料 */
  references?: boolean;
  /** 是否包含文风 */
  styleProfile?: boolean;
  /** 是否包含章节内容 */
  chapterContent?: boolean;
}

const DEFAULT_OPTIONS: Required<ContextBuildOptions> = {
  worldSetting: true,
  storyBackground: true,
  writingBible: true,
  storyProgress: true,
  plotProgress: true,
  characters: true,
  factions: true,
  locations: true,
  items: true,
  glossaries: true,
  outline: true,
  foreshadowings: true,
  references: true,
  styleProfile: true,
  chapterContent: true,
};

/**
 * 构建小说完整上下文（供所有 Agent Node 共享使用）
 */
// @5.4 — 被 @5.7 @5.8 调用
export function buildNovelContext(
  novelData: WritingState["novelData"],
  options: ContextBuildOptions = {}
): string {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  const lines: string[] = [];

  // 世界设定
  if (opts.worldSetting && novelData.worldSetting) {
    lines.push("## 世界设定");
    lines.push(novelData.worldSetting);
    lines.push("");
  }

  // 故事背景
  if (opts.storyBackground && novelData.storyBackground) {
    lines.push("## 故事背景");
    lines.push(novelData.storyBackground);
    lines.push("");
  }

  if (opts.writingBible && novelData.writingBible) {
    const bible = novelData.writingBible;
    lines.push("## 作品圣经");
    if (bible.genre) lines.push("- 题材/频道: " + bible.genre);
    if (bible.targetReaders) lines.push("- 目标读者: " + bible.targetReaders);
    if (bible.coreSellingPoint) lines.push("- 核心卖点: " + bible.coreSellingPoint);
    if (bible.readerPromise) lines.push("- 读者承诺: " + bible.readerPromise);
    if (bible.appealModel) lines.push("- 爽点/情绪收益: " + bible.appealModel);
    if (bible.taboo) lines.push("- 雷点/禁忌: " + bible.taboo);
    if (bible.comparableTitles) lines.push("- 对标方向: " + bible.comparableTitles);
    if (bible.notes) lines.push("- 编辑备注: " + bible.notes);
    lines.push("");
  }

  // 故事进展
  if (opts.storyProgress && novelData.storyProgress) {
    lines.push("## 故事进展");
    lines.push(novelData.storyProgress);
    lines.push("");
  }

  // 剧情进度
  if (opts.plotProgress) {
    lines.push("## 剧情进度");
    lines.push("当前阶段：" + (novelData.plotProgress.currentStage || "未设置"));
    if (novelData.plotProgress.currentGoal) {
      lines.push("当前目标：" + novelData.plotProgress.currentGoal);
    }
    if (novelData.plotProgress.currentConflict) {
      lines.push("当前冲突：" + novelData.plotProgress.currentConflict);
    }
    if (novelData.plotProgress.nextMilestone) {
      lines.push("下一个里程碑：" + novelData.plotProgress.nextMilestone);
    }
    lines.push("");
  }

  // 势力设定
  if (opts.factions && novelData.factions.length > 0) {
    lines.push("## 已有势力");
    for (const f of novelData.factions) {
      lines.push("### " + f.name);
      if (f.aliases) lines.push("- 别名: " + f.aliases);
      if (f.type) lines.push("- 类型: " + f.type);
      if (f.base) lines.push("- 据点: " + f.base.name);
      if (f.description) lines.push("- 描述: " + f.description);
      lines.push("");
    }
  }

  // 角色设定
  if (opts.characters && novelData.characters.length > 0) {
    lines.push("## 已有角色");
    for (const c of novelData.characters) {
      lines.push("### " + c.name);
      if (c.aliases) lines.push("- 别名: " + c.aliases);
      if (c.gender) lines.push("- 性别: " + c.gender);
      if (c.age) lines.push("- 年龄: " + c.age);
      if (c.identity) lines.push("- 身份: " + c.identity);
      if (c.personality) lines.push("- 性格: " + c.personality);
      if (c.appearance) lines.push("- 外貌: " + c.appearance);
      if (c.background) lines.push("- 背景: " + c.background);
      if (c.coreDesire) lines.push("- 核心欲望: " + c.coreDesire);
      if (c.behaviorBoundaries) lines.push("- 行为边界: " + c.behaviorBoundaries);
      if (c.speechStyle) lines.push("- 说话习惯: " + c.speechStyle);
      if (c.relationshipPrinciples) lines.push("- 关系原则: " + c.relationshipPrinciples);
      if (c.shortTermGoal) lines.push("- 短期目标: " + c.shortTermGoal);
      if (c.powerLevel) lines.push("- 实力等级: " + c.powerLevel);
      if (c.combatAbility) lines.push("- 战斗能力: " + c.combatAbility);
      if (c.specialSkills) lines.push("- 特殊技能: " + c.specialSkills);
      if (c.currentStatus) lines.push("- 当前状态: " + c.currentStatus);
      if (c.statusNote) lines.push("- 状态备注: " + c.statusNote);
      if (c.faction) lines.push("- 所属势力: " + c.faction.name);
      if (c.outgoingRelations && c.outgoingRelations.length > 0) {
        const rels = c.outgoingRelations
          .filter(function (r) { return r.target != null; })
          .map(function (r) { return r.target!.name + "(" + r.relationType + ")"; })
          .join(", ");
        lines.push("- 关系: " + rels);
      }
      lines.push("");
    }
  }

  // 地点设定
  if (opts.locations && novelData.locations.length > 0) {
    lines.push("## 已有地点");
    for (const loc of novelData.locations) {
      lines.push("### " + loc.name);
      if (loc.aliases) lines.push("- 别名: " + loc.aliases);
      if (loc.type) lines.push("- 类型: " + loc.type);
      if (loc.climate) lines.push("- 气候: " + loc.climate);
      if (loc.culture) lines.push("- 文化: " + loc.culture);
      if (loc.description) lines.push("- 描述: " + loc.description);
      lines.push("");
    }
  }

  // 物品设定
  if (opts.items && novelData.items.length > 0) {
    lines.push("## 已有物品");
    for (const item of novelData.items) {
      lines.push("### " + item.name);
      if (item.aliases) lines.push("- 别名: " + item.aliases);
      if (item.type) lines.push("- 类型: " + item.type);
      if (item.rarity) lines.push("- 稀有度: " + item.rarity);
      if (item.effect) lines.push("- 效果: " + item.effect);
      if (item.origin) lines.push("- 来历: " + item.origin);
      if (item.description) lines.push("- 描述: " + item.description);
      if (item.owner) lines.push("- 持有者: " + item.owner.name);
      lines.push("");
    }
  }

  // 术语表
  if (opts.glossaries && novelData.glossaries.length > 0) {
    lines.push("## 术语表");
    for (const g of novelData.glossaries) {
      lines.push("- **" + g.term + "**: " + g.definition);
      if (g.category) lines.push("  (分类: " + g.category + ")");
    }
    lines.push("");
  }

  // 大纲
  if (opts.outline) {
    if (novelData.outlineSummary) {
      lines.push("## 大纲概要");
      lines.push(novelData.outlineSummary);
      lines.push("");
    }
    if (novelData.outlineNodes.length > 0) {
      lines.push("## 大纲节点");
      for (const node of novelData.outlineNodes) {
        const statusIcon =
          node.status === "completed" ? "[✓]" :
          node.status === "in_progress" ? "[→]" :
          node.status === "skipped" ? "[×]" : "[○]";
        lines.push(statusIcon + " " + node.title + " (" + (node.kind ?? "stage") + ", " + node.status + ")");
        if (node.content) {
          lines.push("  " + node.content);
        }
      }
      lines.push("");
    }
  }

  // 伏笔
  if (opts.foreshadowings && novelData.foreshadowings.length > 0) {
    lines.push("## 伏笔管理");
    for (const fs of novelData.foreshadowings) {
      lines.push("- " + fs.name + " (" + fs.status + ")");
      if (fs.plantedAt) lines.push("  埋设位置: " + fs.plantedAt);
      if (fs.plantedContent) lines.push("  埋设内容: " + fs.plantedContent);
      if (fs.expectedPayoff) lines.push("  预期回收: " + fs.expectedPayoff);
    }
    lines.push("");
  }

  // 参考资料
  if (opts.references && novelData.references.length > 0) {
    lines.push("## 参考资料");
    for (const ref of novelData.references) {
      lines.push("### " + ref.title + " (" + ref.type + ")");
      lines.push(ref.content);
      lines.push("");
    }
  }

  // 文风
  if (opts.styleProfile && novelData.styleProfile) {
    lines.push("## 应用文风");
    lines.push(novelData.styleProfile);
    lines.push("");
  }

  // 章节内容
  if (opts.chapterContent && novelData.chapterContent) {
    lines.push("## 当前章节内容");
    lines.push(novelData.chapterContent);
    lines.push("");
  }

  if (novelData.approvedBeatPlan) {
    lines.push("## 已批准章节计划");
    lines.push("章节目标：" + novelData.approvedBeatPlan.chapterGoal);
    if (novelData.approvedBeatPlan.mainPlotConnection) {
      lines.push("主线关联：" + novelData.approvedBeatPlan.mainPlotConnection);
    }
    if (novelData.approvedBeatPlan.chapterAcceptanceCriteria) {
      lines.push("验收标准：" + novelData.approvedBeatPlan.chapterAcceptanceCriteria);
    }
    for (const beat of novelData.approvedBeatPlan.sceneBeats) {
      lines.push(`${beat.order}. ${beat.goal}`);
      if (beat.conflict) lines.push("  阻力/冲突：" + beat.conflict);
      if (beat.characters.length > 0) lines.push("  角色：" + beat.characters.join("、"));
      if (beat.foreshadowingRefs?.length) lines.push("  伏笔：" + beat.foreshadowingRefs.join("、"));
      if (beat.estimatedWords) lines.push("  预计字数：" + beat.estimatedWords);
      lines.push("  验收：" + beat.acceptanceCriteria);
    }
    lines.push("");
  }

  return lines.join("\n");
}

/**
 * 构建上下文索引 —— 只告诉 LLM "有哪些数据可用"
 * 约 200-500 token，让 Agent 通过工具自行查询细节
 */
// @5.4 — 被 @5.5 @5.6 调用
export function buildContextIndex(
  novelData: WritingState["novelData"],
): string {
  const lines: string[] = [];
  lines.push("## 数据索引（可通过工具查询详情）");
  lines.push("");

  if (novelData.novelName) {
    lines.push(`- 小说名称：${novelData.novelName}`);
  }
  if (novelData.chapterTitle) {
    lines.push(`- 当前章节：${novelData.chapterTitle}`);
  }

  // 剧情进度摘要
  if (novelData.plotProgress.currentStage) {
    lines.push(`- 剧情阶段：${novelData.plotProgress.currentStage}`);
  }
  if (novelData.plotProgress.currentGoal) {
    lines.push(`- 当前目标：${novelData.plotProgress.currentGoal}`);
  }
  if (novelData.writingBible?.coreSellingPoint) {
    lines.push(`- 核心卖点：${novelData.writingBible.coreSellingPoint}`);
  }
  if (novelData.writingBible?.readerPromise) {
    lines.push(`- 读者承诺：${novelData.writingBible.readerPromise}`);
  }

  // 各数据类型的数量统计
  lines.push("");
  lines.push("### 可用数据");
  if (novelData.characters.length > 0) {
    const names = novelData.characters.map((c) => c.name).join("、");
    lines.push(`- **角色**（${novelData.characters.length}）：${names}`);
  }
  if (novelData.factions.length > 0) {
    const names = novelData.factions.map((f) => f.name).join("、");
    lines.push(`- **势力**（${novelData.factions.length}）：${names}`);
  }
  if (novelData.locations.length > 0) {
    const names = novelData.locations.map((l) => l.name).join("、");
    lines.push(`- **地点**（${novelData.locations.length}）：${names}`);
  }
  if (novelData.items.length > 0) {
    const names = novelData.items.map((i) => i.name).join("、");
    lines.push(`- **物品**（${novelData.items.length}）：${names}`);
  }
  if (novelData.glossaries.length > 0) {
    const terms = novelData.glossaries.map((g) => g.term).join("、");
    lines.push(`- **术语**（${novelData.glossaries.length}）：${terms}`);
  }
  if (novelData.outlineNodes.length > 0) {
    lines.push(`- **大纲节点**（${novelData.outlineNodes.length}）：`);
    for (const node of novelData.outlineNodes) {
      const icon = node.status === "completed" ? "✓" : node.status === "in_progress" ? "→" : "○";
      lines.push(`  ${icon} ${node.title} (${node.kind ?? "stage"})`);
    }
  }
  if (novelData.foreshadowings.length > 0) {
    const active = novelData.foreshadowings.filter((f) => f.status === "active").length;
    lines.push(`- **伏笔**（${novelData.foreshadowings.length}，${active} 活跃）`);
  }
  if (novelData.references.length > 0) {
    const names = novelData.references.map((r) => r.title).join("、");
    lines.push(`- **参考资料**（${novelData.references.length}）：${names}`);
  }
  if (novelData.styleProfile) {
    lines.push("- **文风画像**：已配置（可通过工具查询）");
  }
  if (novelData.approvedBeatPlan) {
    lines.push(`- **已批准章节计划**：${novelData.approvedBeatPlan.chapterGoal}（${novelData.approvedBeatPlan.sceneBeats.length} 个场景节拍）`);
  }

  lines.push("");
  lines.push("需要详细信息时，使用工具查询（如 get_character_detail、get_faction_detail 等）。");

  return lines.join("\n");
}

function compactText(value: string | null | undefined, maxLength = 80): string {
  if (!value) return "";
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > maxLength ? normalized.slice(0, maxLength - 1) + "…" : normalized;
}

function appendHint(parts: string[], label: string, value: string | null | undefined, maxLength = 60) {
  const text = compactText(value, maxLength);
  if (text) parts.push(`${label}：${text}`);
}

/**
 * 构建摘要索引 —— 在只暴露少量简介的前提下，让 Agent 判断是否需要读取详情。
 * 目标不是回答所有问题，而是帮助模型完成“相关性判断”。
 */
// @5.4 — 被 @5.5 @5.6 @5.7 @5.8 @5.9 调用
export function buildSummaryIndex(
  novelData: WritingState["novelData"],
): string {
  const lines: string[] = [];
  lines.push("## 摘要索引（先读这里，再决定是否查详情）");
  lines.push("");

  if (novelData.novelName) lines.push(`- 小说：${novelData.novelName}`);
  if (novelData.chapterTitle) lines.push(`- 当前章节：${novelData.chapterTitle}`);
  if (novelData.plotProgress.currentStage) lines.push(`- 剧情阶段：${novelData.plotProgress.currentStage}`);
  if (novelData.plotProgress.currentGoal) lines.push(`- 当前目标：${compactText(novelData.plotProgress.currentGoal, 90)}`);

  if (novelData.characters.length > 0) {
    lines.push("");
    lines.push("### 角色索引");
    for (const c of novelData.characters) {
      const parts: string[] = [];
      appendHint(parts, "别名", c.aliases, 30);
      appendHint(parts, "身份", c.identity, 40);
      if (c.faction?.name) parts.push(`势力：${c.faction.name}`);
      appendHint(parts, "性格", c.personality, 50);
      appendHint(parts, "核心欲望", c.coreDesire, 45);
      appendHint(parts, "行为边界", c.behaviorBoundaries, 45);
      appendHint(parts, "短期目标", c.shortTermGoal, 40);
      appendHint(parts, "状态", c.statusNote || c.currentStatus, 40);
      lines.push(`- ${c.name}${parts.length ? "：" + parts.join("；") : ""}`);
    }
  }

  if (novelData.factions.length > 0) {
    lines.push("");
    lines.push("### 势力索引");
    for (const f of novelData.factions) {
      const parts: string[] = [];
      appendHint(parts, "别名", f.aliases, 30);
      appendHint(parts, "类型", f.type, 30);
      if (f.base?.name) parts.push(`据点：${f.base.name}`);
      appendHint(parts, "简介", f.description, 70);
      lines.push(`- ${f.name}${parts.length ? "：" + parts.join("；") : ""}`);
    }
  }

  if (novelData.locations.length > 0) {
    lines.push("");
    lines.push("### 地点索引");
    for (const l of novelData.locations) {
      const parts: string[] = [];
      appendHint(parts, "别名", l.aliases, 30);
      appendHint(parts, "类型", l.type, 30);
      appendHint(parts, "气候", l.climate, 30);
      appendHint(parts, "简介", l.description, 70);
      lines.push(`- ${l.name}${parts.length ? "：" + parts.join("；") : ""}`);
    }
  }

  if (novelData.items.length > 0) {
    lines.push("");
    lines.push("### 物品索引");
    for (const i of novelData.items) {
      const parts: string[] = [];
      appendHint(parts, "别名", i.aliases, 30);
      appendHint(parts, "类型", i.type, 30);
      appendHint(parts, "效果", i.effect, 50);
      if (i.owner?.name) parts.push(`持有者：${i.owner.name}`);
      appendHint(parts, "简介", i.description, 60);
      lines.push(`- ${i.name}${parts.length ? "：" + parts.join("；") : ""}`);
    }
  }

  if (novelData.glossaries.length > 0) {
    lines.push("");
    lines.push("### 术语索引");
    for (const g of novelData.glossaries) {
      const category = g.category ? `（${g.category}）` : "";
      lines.push(`- ${g.term}${category}：${compactText(g.definition, 70)}`);
    }
  }

  if (novelData.outlineNodes.length > 0) {
    lines.push("");
    lines.push("### 大纲索引");
    for (const node of novelData.outlineNodes) {
      const icon = node.status === "completed" ? "✓" : node.status === "in_progress" ? "→" : "○";
      lines.push(`- ${icon} ${node.title} (${node.kind ?? "stage"})${node.content ? "：" + compactText(node.content, 70) : ""}`);
    }
  }

  if (novelData.foreshadowings.length > 0) {
    lines.push("");
    lines.push("### 伏笔索引");
    for (const f of novelData.foreshadowings) {
      const parts = [`状态：${f.status}`];
      appendHint(parts, "埋设", f.plantedContent || f.plantedAt, 55);
      appendHint(parts, "回收", f.expectedPayoff || f.payoffAt, 55);
      lines.push(`- ${f.name}：${parts.join("；")}`);
    }
  }

  if (novelData.approvedBeatPlan) {
    lines.push("");
    lines.push("### 已批准章节计划");
    lines.push(`- 章节目标：${compactText(novelData.approvedBeatPlan.chapterGoal, 100)}`);
    if (novelData.approvedBeatPlan.mainPlotConnection) {
      lines.push(`- 主线关联：${compactText(novelData.approvedBeatPlan.mainPlotConnection, 100)}`);
    }
    for (const beat of novelData.approvedBeatPlan.sceneBeats) {
      const parts = [
        compactText(beat.goal, 80),
        beat.conflict ? `阻力：${compactText(beat.conflict, 60)}` : "",
        beat.characters.length ? `角色：${beat.characters.join("、")}` : "",
        beat.foreshadowingRefs?.length ? `伏笔：${beat.foreshadowingRefs.join("、")}` : "",
        beat.estimatedWords ? `约${beat.estimatedWords}字` : "",
        beat.acceptanceCriteria ? `验收：${compactText(beat.acceptanceCriteria, 50)}` : "",
      ].filter(Boolean);
      lines.push(`- ${beat.order}. ${parts.join("；")}`);
    }
  }

  lines.push("");
  lines.push("读取规则：摘要索引用于判断相关性；只有摘要不足以支持事实判断、冲突校验或精确改写时，才调用详情工具。");

  return lines.join("\n");
}

/**
 * 构建极简上下文 —— 仅小说名、章节名、剧情阶段
 * 约 100-200 token
 */
export function buildMinimalContext(
  novelData: WritingState["novelData"],
): string {
  const lines: string[] = [];
  lines.push(`小说：${novelData.novelName || "未知"}`);
  if (novelData.chapterTitle) {
    lines.push(`章节：${novelData.chapterTitle}`);
  }
  if (novelData.plotProgress.currentStage) {
    lines.push(`剧情阶段：${novelData.plotProgress.currentStage}`);
  }
  if (novelData.outlineSummary) {
    lines.push(`大纲概要：${novelData.outlineSummary}`);
  }
  return lines.join("\n");
}

/**
 * 构建当前任务上下文。
 *
 * 这段上下文用于 Agent 间转交后的目标 Agent。原始用户输入是上层约束，
 * pendingAgentCall 是本轮直接任务，二者都不能只依赖对话历史隐式传递。
 */
export function buildActiveTaskContext(state: WritingState): string {
  const lines: string[] = [];
  const rootRequest = state.userMessage?.trim();
  const call = state.pendingAgentCall;
  const operation = state.currentOperation;

  const activeArtifactId = getActiveArtifactId(state)?.trim();

  if (!rootRequest && !call && !operation && !activeArtifactId) return "";

  lines.push("## 当前任务上下文");
  lines.push("");

  if (rootRequest) {
    lines.push("### 根用户请求");
    lines.push(rootRequest);
    lines.push("");
  }

  if (operation) {
    lines.push("### 当前 CreativeOperation");
    lines.push(`- 操作类型：${operation.kind}`);
    lines.push(`- 操作目标：${operation.targetType}${operation.targetId ? ` (${operation.targetId})` : ""}`);
    lines.push(`- 用户目标：${operation.userGoal}`);
    lines.push(`- 主责 Agent：${operation.primaryAgent}`);
    if (operation.reviewers.length > 0) {
      lines.push(`- 建议审核角色：${operation.reviewers.join("、")}`);
    }
    lines.push(`- 预期产物：${operation.outputKind}`);
    lines.push(`- 需要待审核草案：${operation.requiresArtifact ? "是" : "否"}`);
    lines.push(`- 需要用户确认：${operation.requiresUserApproval ? "是" : "否"}`);
    lines.push(`- 识别依据：${operation.reasoning}`);
    lines.push("");
    lines.push("执行要求：优先完成 CreativeOperation 的主产物；需要落库的设定/大纲/伏笔变更必须走 ReviewArtifact，不要直接当作正式事实写入。");
    lines.push("");
  }

  if (call) {
    lines.push("### 本轮直接任务");
    lines.push(`- 调用来源：${call.fromAgent}`);
    lines.push(`- 目标 Agent：${call.toAgent}`);
    lines.push(`- 调用原因：${call.reason}`);
    if (call.specificQuestion) {
      lines.push(`- 具体要求：${call.specificQuestion}`);
    }
    if (call.contentToRewrite) {
      lines.push("");
      lines.push("### 待处理材料");
      lines.push(call.contentToRewrite);
    }
    lines.push("");
    lines.push("执行要求：优先完成“本轮直接任务”，同时不得违反“根用户请求”中的流程约束。");
  }

  if (activeArtifactId) {
    lines.push("");
    lines.push("### 当前待审核草案");
    lines.push(`- artifactId：${activeArtifactId}`);
    lines.push("- 以下关联产物是待审核草案，不是正式设定。评审和返工必须引用 artifactId 与 revision；除非用户确认应用，否则不得把它当成已落库事实。");
    lines.push("- 需要查看草案详情时，调用 get_active_review_artifact 或 get_review_artifact。");
  }

  return lines.join("\n");
}

/**
 * 构建对话历史文本
 */
export interface ConversationHistoryTextOptions {
  mode?: "full" | "reviewer";
  activeArtifactId?: string | null;
  artifactProducerAgentId?: CoreAgentId | null;
  reviewerAgentOutputMaxChars?: number;
}

export function buildConversationHistoryText(
  conversationHistory: WritingState["conversationHistory"],
  options: ConversationHistoryTextOptions = {}
): string {
  if (conversationHistory.length === 0) return "";

  const lines: string[] = [];
  const reviewerMode = options.mode === "reviewer";
  const maxAgentChars = options.reviewerAgentOutputMaxChars ?? 800;
  let artifactMarkerAdded = false;
  for (const msg of conversationHistory) {
    if (msg.userMessage) {
      lines.push("**用户**：" + msg.userMessage);
    } else if (msg.isCallMessage) {
      const target = msg.callTarget ? ` → ${msg.callTarget}` : "";
      lines.push("**" + msg.agentName + " 调用" + target + "**：" + msg.content);
    } else if (msg.agentOutput?.content) {
      if (reviewerMode && msg.agentId === options.artifactProducerAgentId) {
        if (!artifactMarkerAdded) {
          const artifactLabel = options.activeArtifactId ? `（artifactId：${options.activeArtifactId}）` : "";
          lines.push(`**${msg.agentName}**：已提交当前待审核草案${artifactLabel}，正文请通过 get_active_review_artifact 读取。`);
          artifactMarkerAdded = true;
        }
      } else {
        const content = reviewerMode && msg.agentOutput.content.length > maxAgentChars
          ? msg.agentOutput.content.slice(0, maxAgentChars) + `\n[历史输出已截断，原长度 ${msg.agentOutput.content.length} 字符]`
          : msg.agentOutput.content;
        lines.push("**" + msg.agentName + "**：" + content);
      }
    }
    lines.push("");
  }
  return lines.join("\n");
}

/**
 * 获取大纲状态图标
 */
export function getOutlineStatusIcon(status: string): string {
  switch (status) {
    case "completed": return "[✓]";
    case "in_progress": return "[→]";
    case "skipped": return "[×]";
    default: return "[○]";
  }
}
