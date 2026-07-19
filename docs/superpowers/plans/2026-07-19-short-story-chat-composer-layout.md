# 中短篇新对话输入区布局修正 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复中短篇新对话输入控件被拉满高度的问题。

**Architecture:** 将右侧对话面板从依赖可选子节点位置的固定 Grid 改为纵向 Flex。消息区负责伸展和滚动，输入区只保持内容高度，发送按钮由独立操作行右对齐。

**Tech Stack:** React、TypeScript、原生 CSS、Node Test Runner。

---

### Task 1: 建立布局回归契约

**Files:**
- Modify: `apps/web/src/features/workspace/__tests__/short-story-layout-source.test.ts`

- [ ] **Step 1: 写入失败测试**

断言对话面板使用纵向 Flex，消息区具有 `flex: 1` 和 `min-height: 0`，输入区没有伸展规则，发送按钮位于右对齐操作行。

- [ ] **Step 2: 验证测试失败**

Run: `npm test --workspace @inkforge/web -- --test-name-pattern="中短篇新对话输入区保持紧凑"`

Expected: FAIL，现有 CSS 仍使用固定 Grid 且 JSX 没有操作行。

### Task 2: 修复右栏内部布局

**Files:**
- Modify: `apps/web/src/features/workspace/short-story/short-story-chat-pane.tsx`
- Modify: `apps/web/src/features/workspace/short-story/short-story-workspace.css`

- [ ] **Step 1: 实现最小修正**

将 `.short-story-chat-pane` 改为纵向 Flex；让 `.short-story-chat-messages` 使用 `flex: 1` 和 `min-height: 0`；为发送按钮增加 `.short-story-chat-actions` 包裹层并右对齐。

- [ ] **Step 2: 验证回归测试通过**

Run: `npm test --workspace @inkforge/web -- --test-name-pattern="中短篇新对话输入区保持紧凑"`

Expected: PASS。

### Task 3: 页面与项目验证

**Files:**
- Verify: `apps/web/src/features/workspace/short-story/short-story-chat-pane.tsx`
- Verify: `apps/web/src/features/workspace/short-story/short-story-workspace.css`

- [ ] **Step 1: 真实页面验证**

打开指定中短篇工作区，新建对话，确认模式按钮、五行输入框和发送按钮均保持紧凑；打开历史列表后布局仍稳定。

- [ ] **Step 2: 运行前端检查**

Run: `npm run test:web && npm run typecheck && npm run lint && npm run build`

Expected: 所有命令退出码为 0。

- [ ] **Step 3: 提交**

```bash
git add docs/specs/2026-07-19-short-story-resizable-panels.md docs/superpowers/specs/2026-07-19-short-story-chat-composer-layout-design.md docs/superpowers/plans/2026-07-19-short-story-chat-composer-layout.md apps/web/src/features/workspace/__tests__/short-story-layout-source.test.ts apps/web/src/features/workspace/short-story/short-story-chat-pane.tsx apps/web/src/features/workspace/short-story/short-story-workspace.css
git commit -m "修复：恢复中短篇新对话紧凑布局"
```
