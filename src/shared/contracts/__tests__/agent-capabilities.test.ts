/**
 * Agent 能力卡测试。
 *
 * 运行方式：npx tsx --test src/shared/contracts/__tests__/agent-capabilities.test.ts
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { ALL_CORE_AGENT_IDS } from "../agent";
import {
  AGENT_CAPABILITY_CARDS,
  buildIntentClassifierSystemPrompt,
  formatAgentCapabilityCards,
  formatSingleAgentCapabilityCard,
} from "../agent-capabilities";

describe("Agent capability cards", () => {
  it("覆盖全部核心 Agent", () => {
    assert.deepEqual(Object.keys(AGENT_CAPABILITY_CARDS).sort(), [...ALL_CORE_AGENT_IDS].sort());
  });

  it("能力卡文本包含每个 Agent 的职责和保存边界", () => {
    const text = formatAgentCapabilityCards();
    for (const id of ALL_CORE_AGENT_IDS) {
      assert.ok(text.includes(`### ${id}`), `缺少 ${id} 能力卡`);
      assert.ok(text.includes(AGENT_CAPABILITY_CARDS[id].mission), `缺少 ${id} 职责说明`);
    }
    assert.ok(text.includes("outlineAdjustments"));
    assert.ok(text.includes("characterExperiences"));
  });

  it("可按需读取单个 Agent 能力卡", () => {
    const text = formatSingleAgentCapabilityCard("编辑");
    assert.ok(text.includes("### 编辑"));
    assert.ok(text.includes("网文编辑"));
    assert.ok(text.includes("可保存 updates section：无保存型 updates"));
    assert.equal(text.includes("### 设定"), false);
  });

  it("初始分类器 prompt 使用能力卡而不是固定关键词规则", () => {
    const prompt = buildIntentClassifierSystemPrompt();
    assert.ok(prompt.includes("Agent 能力卡"));
    assert.ok(prompt.includes("主责 Agent"));
    assert.ok(prompt.includes('"targetAgent"'));
    assert.equal(prompt.includes("用户讨论大纲/剧情走向/伏笔时 → 剧情"), false);
  });
});
