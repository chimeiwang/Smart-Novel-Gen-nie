# 中短篇工作区布局修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复中短篇工作区顶部纵向错位，并扩大右侧作品信息与审核栏。

**Architecture:** 只修改中短篇工作区的局部 CSS，不改变组件树和业务状态。用源码回归测试锁定关键布局声明，再用真实开发页面测量元素边界和视觉截图完成验收。

**Tech Stack:** Next.js 16、React、原生 CSS、Node.js `node:test`、应用内浏览器。

---

### Task 1: 锁定布局契约

**Files:**
- Create: `apps/web/src/features/workspace/__tests__/short-story-layout-source.test.ts`
- Modify: `apps/web/src/features/workspace/short-story/short-story-workspace.css`

- [x] **Step 1: 写失败测试**

测试读取 `short-story-workspace.css`，断言顶部声明 `flex-direction: row`，默认右栏为 `400px`，大屏右栏为 `420px`，窄桌面右栏为 `360px`。

- [x] **Step 2: 运行测试并确认失败**

Run: `npm test --workspace @inkforge/web -- src/features/workspace/__tests__/short-story-layout-source.test.ts`

Expected: FAIL，提示缺少横向方向或新的检查栏宽度。

- [x] **Step 3: 写最小 CSS 修复**

为 `.short-story-header` 增加横向方向、最小高度和账户浮层预留；为标题组增加 `min-width: 0`。调整默认、超宽屏和窄桌面的三栏列宽，不修改正文排版规则。

- [x] **Step 4: 运行测试并确认通过**

Run: `npm test --workspace @inkforge/web -- src/features/workspace/__tests__/short-story-layout-source.test.ts`

Expected: PASS。

### Task 2: 回归与真实页面验收

**Files:**
- Verify: `apps/web/src/features/workspace/short-story/short-story-workspace.css`
- Verify: `apps/web/src/features/workspace/__tests__/short-story-layout-source.test.ts`

- [x] **Step 1: 运行前端测试**

Run: `npm run test:web`

Expected: 所有测试通过。

- [x] **Step 2: 运行静态检查**

Run: `npm run typecheck && npm run lint`

Expected: 两条命令退出码均为 0。

- [x] **Step 3: 在真实开发页面测量布局**

打开 `http://localhost:43119/workspace/cmrr95evcqoirfnay34rzvuej`，在 1280px 视口确认顶部子元素同一行、中央区域至少 600px、右栏 360px；在宽屏确认右栏 420px。

- [x] **Step 4: 保存视觉证据**

截取修复后的工作区页面，确认标题靠左、退出靠右、作品信息与审核内容不再过窄。

### Task 3: 顶部左侧信息组单行排列

**Files:**
- Modify: `apps/web/src/features/workspace/short-story/short-story-workspace.tsx`
- Modify: `apps/web/src/features/workspace/short-story/short-story-workspace.css`
- Modify: `apps/web/src/features/workspace/__tests__/short-story-layout-source.test.ts`

- [x] **Step 1: 增加失败测试**

断言顶部左侧容器具有独立语义类，并明确使用不换行的横向 flex 布局。

- [x] **Step 2: 实现最小布局修改**

为左侧容器增加语义类；让“返回”、作品标题和状态标签保持同一行，长标题仅对自身做省略。

- [x] **Step 3: 回归与真实页面验收**

运行相关测试、完整前端测试、类型检查和 lint，并在真实开发页面测量三个元素是否处于同一行。
