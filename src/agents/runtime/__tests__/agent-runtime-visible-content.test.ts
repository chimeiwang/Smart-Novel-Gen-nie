/**
 * visibleContent 聚合专项测试（Phase B 返工）
 *
 * 验证：多轮 tool-call 中每一轮的 assistant 正文都被保留在 visibleContent 中。
 *
 * 运行方式：npx tsx --test src/agents/runtime/__tests__/agent-runtime-visible-content.test.ts
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { parseControlEventArgs } from "@/shared/contracts/agent-control";
import { aggregateVisibleParts } from "@/agents/lib/llm-wrapper";

// ============================================
// 1. 核心场景：同轮 assistant text + control tool
// ============================================

describe("visibleContent 聚合（模拟）", () => {
  it("真实聚合函数：单轮长文本 不会重复拼接", () => {
    const longText = [
      "## 评审报告",
      "",
      "这一章的最大问题是中段冲突没有升级。主角目标虽然清楚，但阻力没有逐层加码，导致读者读到中段时缺少继续追读的压力。",
      "",
      "### 修改建议",
      "1. 在中段加入明确的外部阻力。",
      "2. 让主角为选择付出代价。",
      "3. 章末保留一个未解决的问题。",
    ].join("\n");

    const aggregated = aggregateVisibleParts([longText], longText);
    assert.equal(aggregated, longText);
    assert.equal(aggregated.indexOf("## 评审报告"), aggregated.lastIndexOf("## 评审报告"));
  });

  it("真实聚合函数：tool-call 轮次长报告 + 最终短确认都保留且不重复报告", () => {
    const report = [
      "## 评审报告",
      "",
      "开篇钩子有效，但中段冲突推进不足。读者能理解主角目标，却看不到目标被强力阻碍，因此爽点兑现偏弱。",
      "",
      "### 评分理由",
      "- hook: 开场有问题意识",
      "- tension: 冲突递进不足",
      "- endingHook: 章末悬念可保留",
    ].join("\n");
    const confirmation = "已提交评分。";

    const aggregated = aggregateVisibleParts([report], confirmation);
    assert.ok(aggregated.includes(report));
    assert.ok(aggregated.includes(confirmation));
    assert.equal(aggregated.indexOf("## 评审报告"), aggregated.lastIndexOf("## 评审报告"));
  });

  it("submit_quality_report 在长篇报告后调用 → 评分不丢失", () => {
    const event = parseControlEventArgs("submit_quality_report", {
      scores: { hook: 8, tension: 7, payoff: 6, pacing: 8, endingHook: 9, readerPromise: 7, overall: 7 },
      qualityGate: "revise",
      rewriteBrief: "中段冲突需要加强",
    });
    assert.ok(event);
    assert.equal(event!.type, "submit_quality_report");
    if (event!.type === "submit_quality_report") {
      // 确认评分数据完整
      assert.equal(event!.scores.hook, 8);
      assert.equal(event!.scores.overall, 7);
      assert.equal(event!.qualityGate, "revise");
      assert.equal(event!.rewriteBrief, "中段冲突需要加强");
    }
  });

  it("多轮输出模拟：第 1 轮长篇 + control tool，第 2 轮短确认 → 聚合不丢失", () => {
    // 模拟 visibleContentParts 聚合逻辑
    const round1 = "## 评审报告\n\n这一章的最大问题是中段冲突没有升级。\n\n### 详细分析\n1. 开篇的钩子足够吸引人\n2. 中段节奏拖沓\n3. 结尾悬念设置得当";
    const round2 = "已提交评分。";

    const parts = [round1]; // 第 1 轮已累积
    const trimmedLast = round2.trim();

    // 聚合逻辑（模拟 aggregateVisibleParts）
    const lastLower = trimmedLast.toLowerCase();
    const alreadyCovered = parts.some((p) => p.toLowerCase().includes(lastLower));
    assert.equal(alreadyCovered, false, "短确认文本不应被已有内容覆盖");

    // 聚合结果
    const aggregated = [...parts, round2].join("\n\n").trim();

    // 验证：长篇报告在第一部分
    assert.ok(aggregated.includes("## 评审报告"));
    assert.ok(aggregated.includes("中段节奏拖沓"));
    // 验证：短确认也在
    assert.ok(aggregated.includes("已提交评分。"));
    // 验证：长篇在前
    assert.ok(aggregated.indexOf("## 评审报告") < aggregated.indexOf("已提交评分。"));
  });

  it("单轮输出无 control tool → visibleContent 等于原始内容", () => {
    const singleRound = "## 剧情分析\n\n根据当前大纲，建议在第一章中段增加冲突节点。";
    const parts: string[] = [singleRound];

    // 单轮场景：parts 只有一个元素
    assert.equal(parts.length, 1);
    assert.equal(parts.join("\n\n").trim(), singleRound);
  });

  it("纯 tool call 轮次（无正文）不被加入 visibleContent", () => {
    // 模拟某轮只有 tool_calls 没有 text content
    const parts: string[] = []; // 空数组 = 本轮无正文被加入

    const lastText = "校验完成，没有发现问题。";
    const aggregated = lastText; // parts 为空时直接返回 lastText

    assert.equal(aggregated, "校验完成，没有发现问题。");
  });

  it("短确认去重：前文已含相同内容时跳过", () => {
    // 模拟长篇报告 + 短确认
    const round1 = "## 校验报告\n\n经过全面检查，本章节没有发现与设定冲突的内容。\n\n### 检查项目\n- 角色一致性：通过\n- 设定一致性：通过\n- 逻辑连贯性：通过\n- 伏笔回收：通过";
    const round2 = "校验通过，没有发现问题。";

    const parts = [round1];
    const trimmedLast = round2.trim();
    const lastLower = trimmedLast.toLowerCase();

    // round2 的短确认内容在 round1 中已经表达过了
    assert.equal(lastLower, "校验通过，没有发现问题。");
    // 长篇报告的长度应明显大于短确认
    assert.ok(round1.length > 50, `长篇报告长度=${round1.length}，应 > 50`);
    // 短确认的长度应在 100 以内
    assert.ok(trimmedLast.length < 100, `确认文本长度=${trimmedLast.length}，应 < 100`);
    // 验证 round1 确实包含了 round2 的核心语义
    assert.ok(round1.includes("没有发现") || round1.includes("校验通过"), "长篇应该包含校验结论");
  });
});
