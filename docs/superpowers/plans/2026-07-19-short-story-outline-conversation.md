# 中短篇改纲对话 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在中短篇工作区提供可刷新恢复、可连续提交、能关联完整大纲版本的改纲对话。

**Architecture:** 继续复用 WritingMessage 和 ReviewArtifactRevision，不修改数据库和公共契约。新增纯函数把当前大纲的 `revision_focus` 消息与版本摘要合并为对话条目，再由独立 React 组件渲染；工作区只负责请求、状态和既有决策调用。

**Tech Stack:** Next.js 16、React、TypeScript、原生 CSS、生成的 OpenAPI 客户端、Node test runner。

---

### Task 1: 对话投影规则

**Files:**
- Create: `apps/web/src/features/workspace/short-story/short-story-outline-conversation-model.ts`
- Test: `apps/web/src/features/workspace/__tests__/short-story-outline-conversation-model.test.ts`

- [x] **Step 1: 写失败测试**

覆盖同一 Artifact 消息过滤、`sourceRevision` 到结果 revision 的关联、初始版本、处理中、内容未变化和历史缺失消息六种情况。

- [x] **Step 2: 验证测试失败**

Run: `node --test --experimental-strip-types apps/web/src/features/workspace/__tests__/short-story-outline-conversation-model.test.ts`

Expected: FAIL，模块尚不存在。

- [x] **Step 3: 实现纯函数**

导出 `buildShortStoryOutlineConversation()`，返回带稳定 key、角色、正文、来源版本、结果版本、状态和时间的有序条目。只读取合法对象 metadata，遇到旧数据或非法 metadata 时安全忽略。

- [x] **Step 4: 验证测试通过**

Run: `node --test --experimental-strip-types apps/web/src/features/workspace/__tests__/short-story-outline-conversation-model.test.ts`

Expected: PASS。

### Task 2: 对话组件与样式

**Files:**
- Create: `apps/web/src/features/workspace/short-story/short-story-outline-conversation.tsx`
- Modify: `apps/web/src/features/workspace/short-story/short-story-workspace.css`
- Test: `apps/web/src/features/workspace/__tests__/short-story-outline-conversation-source.test.ts`

- [x] **Step 1: 写失败的源码契约测试**

断言组件包含“改纲对话”“发送修改要求”、用户/Agent 结果语义标签、只读提示以及版本选择回调。

- [x] **Step 2: 验证测试失败**

Run: `node --test --experimental-strip-types apps/web/src/features/workspace/__tests__/short-story-outline-conversation-source.test.ts`

Expected: FAIL，组件尚不存在。

- [x] **Step 3: 实现组件和原生 CSS**

组件按正序渲染消息气泡与版本结果卡片，历史区域独立滚动；仅在可修改状态显示 textarea 和发送按钮，其他状态显示明确只读说明。

- [x] **Step 4: 验证测试通过**

Run: `node --test --experimental-strip-types apps/web/src/features/workspace/__tests__/short-story-outline-conversation-source.test.ts`

Expected: PASS。

### Task 3: 接入工作区和现有决策流

**Files:**
- Modify: `apps/web/src/features/workspace/short-story/short-story-workspace.tsx`
- Modify: `apps/web/src/features/workspace/__tests__/short-story-api-source.test.ts`

- [x] **Step 1: 写失败的接入测试**

断言工作区读取 `/api/v1/writing/sessions/{session_id}`、构建对话、渲染新组件，并在 revise 请求接受后清空输入。

- [x] **Step 2: 验证测试失败**

Run: `node --test --experimental-strip-types apps/web/src/features/workspace/__tests__/short-story-api-source.test.ts`

Expected: FAIL，工作区尚未读取会话详情。

- [x] **Step 3: 接入会话读取**

当大纲页可见且会话、Artifact 或任务时间变化时刷新会话消息；会话错误只影响对话区域，不覆盖整个工作区。把原一次性改纲 textarea 替换为对话组件，批准、放弃和版本历史保留原行为。

- [x] **Step 4: 接入发送与版本选择**

复用既有 `decideArtifact(..., "revise", userMessage)`；请求接受后清空输入，并让版本结果卡片调用既有 `loadRevision()`。

- [x] **Step 5: 验证接入测试通过**

Run: `node --test --experimental-strip-types apps/web/src/features/workspace/__tests__/short-story-api-source.test.ts`

Expected: PASS。

### Task 4: 回归和浏览器验收

**Files:**
- Modify: `docs/specs/2026-07-19-short-story-outline-conversation.md`

- [x] **Step 1: 运行前端回归**

Run: `npm run test:web`

Expected: 全部通过。

- [x] **Step 2: 运行静态检查**

Run: `npm run typecheck`

Run: `npm run lint`

Expected: 全部通过。

- [x] **Step 3: 在开发服务验证真实页面**

打开现有中短篇工作区，确认真实 LLM 历史版本形成只读对话且刷新可恢复；连续两轮、继续输入和版本关联使用同一生产组件的自动化测试覆盖，避免额外创建验收作品消耗用户额度。

- [x] **Step 4: 更新规格状态**

把规格状态改为“实现完成”，记录真实页面验收结果；若真实 LLM 运行受外部供应商限制，明确保留失败证据，不把静态测试冒充端到端通过。
