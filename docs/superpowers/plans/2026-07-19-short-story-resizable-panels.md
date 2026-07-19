# 中短篇三栏宽度调整 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使用成熟分栏组件为中短篇工作区增加有边界、可持久化的三栏宽度调整。

**Architecture:** `ShortStoryResizableLayout` 封装 `react-resizable-panels` 的 Group、Panel 和 Separator，只负责布局与存储；`ShortStoryWorkspace` 继续负责业务内容。纯函数模块负责存储键和安全解析，使浏览器存储失败不影响页面。

**Tech Stack:** React 19、Next.js 16、TypeScript、原生 CSS、react-resizable-panels 4。

---

### Task 1: 布局契约与浏览器存储

**Files:**
- Create: `apps/web/src/features/workspace/short-story/short-story-panel-layout.ts`
- Create: `apps/web/src/features/workspace/__tests__/short-story-panel-layout.test.ts`

- [ ] **Step 1: 写入失败测试**

测试默认约束、按小说隔离的存储键、合法布局解析，以及损坏数据和存储异常回退。

- [ ] **Step 2: 验证测试因模块不存在而失败**

Run: `npm test --workspace @inkforge/web -- --test-name-pattern="中短篇分栏布局"`

- [ ] **Step 3: 实现最小纯函数模块**

导出三个稳定 panel ID、左右栏约束、`buildShortStoryPanelStorageKey()`、`readShortStoryPanelLayout()` 和 `writeShortStoryPanelLayout()`；所有存储调用以 `try/catch` 降级。

- [ ] **Step 4: 验证单元测试通过**

Run: `npm test --workspace @inkforge/web -- --test-name-pattern="中短篇分栏布局"`

### Task 2: 第三方分栏组件

**Files:**
- Modify: `apps/web/package.json`
- Modify: `package-lock.json`
- Create: `apps/web/src/features/workspace/short-story/short-story-resizable-layout.tsx`
- Modify: `apps/web/src/features/workspace/short-story/short-story-workspace.tsx`
- Modify: `apps/web/src/features/workspace/short-story/short-story-workspace.css`
- Modify: `apps/web/src/features/workspace/__tests__/short-story-layout-source.test.ts`

- [ ] **Step 1: 写入失败的源码契约测试**

断言工作区使用 `ShortStoryResizableLayout`，该组件导入 `Group`、`Panel`、`Separator`，声明像素最小/最大宽度和 `onLayoutChanged`，且没有任何自写指针拖动事件。

- [ ] **Step 2: 验证源码契约测试失败**

Run: `npm test --workspace @inkforge/web -- --test-name-pattern="中短篇三栏"`

- [ ] **Step 3: 安装并接入第三方组件**

Run: `npm install react-resizable-panels@^4.12.2 --workspace @inkforge/web`

把现有左栏、中栏、右栏作为三个 children 传给新组件。左栏使用 `220/280/360px`，中栏最小 `640px`，右栏使用 `320/400/520px`；在 `onLayoutChanged` 中保存最终布局。

- [ ] **Step 4: 设置分隔线样式**

删除 `.short-story-grid` 的固定 CSS Grid 列定义和宽屏列覆盖；保留高度、最小高度与各栏滚动。增加分隔条 hover、active、focus-visible 样式，不覆盖组件的 ARIA 属性和命中行为。

- [ ] **Step 5: 验证相关测试通过**

Run: `npm test --workspace @inkforge/web -- --test-name-pattern="中短篇三栏|中短篇分栏布局"`

### Task 3: 回归和真实页面验收

**Files:**
- Verify only

- [ ] **Step 1: 运行完整前端验证**

Run: `npm run test:web && npm run typecheck && npm run lint && npm run build`

- [ ] **Step 2: 在真实工作区拖动验收**

打开用户指定的中短篇工作区，拖动左右分隔线到最大边界，确认两侧宽度受限；刷新页面，确认布局自动恢复；检查控制台无错误。

- [ ] **Step 3: 检查差异范围**

Run: `git diff --check && git status --short`

确认未修改 PostgreSQL schema、长篇工作区和用户已有的未提交文件。
