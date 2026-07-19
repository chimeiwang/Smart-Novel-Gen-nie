# 中短篇对话消息自然高度 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 防止单条中短篇对话消息被拉伸到消息记录区全高。

**Architecture:** 保留现有 Grid 消息列表，在容器上显式使用顶部内容对齐，让隐式轨道维持内容自然高度。通过 CSS 源码回归测试固定该约束。

**Tech Stack:** 原生 CSS、Node Test Runner。

---

### Task 1: 建立并修复消息高度回归

**Files:**
- Modify: `apps/web/src/features/workspace/__tests__/short-story-layout-source.test.ts`
- Modify: `apps/web/src/features/workspace/short-story/short-story-workspace.css`

- [ ] **Step 1: 写入失败测试**

在布局源码测试中断言 `.short-story-chat-messages` 同时包含 `display: grid` 和 `align-content: start`。

- [ ] **Step 2: 验证测试失败**

Run: `npx tsx --test apps/web/src/features/workspace/__tests__/short-story-layout-source.test.ts`

Expected: FAIL，现有消息列表缺少 `align-content: start`。

- [ ] **Step 3: 实现最小修正**

在 `.short-story-chat-messages` 中增加：

```css
align-content: start;
```

- [ ] **Step 4: 验证目标测试和页面**

运行目标测试，并在指定中短篇工作区确认单条消息卡片按内容自然高度显示。

- [ ] **Step 5: 运行完整前端检查**

Run: `npm run test:web && npm run typecheck && npm run lint && npm run build`

Expected: 所有命令退出码为 0。
