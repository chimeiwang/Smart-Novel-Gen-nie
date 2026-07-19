# 中短篇工作区中文状态文案实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除中短篇工作区直接展示的英文操作、阶段、审核结论和版本术语。

**Architecture:** 保留服务端英文枚举作为稳定契约，在前端增加单一展示文案模块。组件只消费格式化后的中文文案，未知值使用中文兜底且不泄漏原值。

**Tech Stack:** TypeScript、React、Next.js 16、Node.js `node:test`。

---

### Task 1: 建立中文展示映射

**Files:**
- Create: `apps/web/src/features/workspace/short-story/short-story-display-labels.ts`
- Create: `apps/web/src/features/workspace/__tests__/short-story-display-labels.test.ts`

- [x] **Step 1: 写失败测试**

覆盖两个中短篇操作、常见任务阶段、三种审核结论、未知阶段中文兜底和版本号格式。

- [x] **Step 2: 运行测试并确认失败**

Run: `npm exec --workspace @inkforge/web -- tsx --test src/features/workspace/__tests__/short-story-display-labels.test.ts`

Expected: FAIL，提示展示文案模块尚不存在。

- [x] **Step 3: 实现最小映射模块**

使用生成客户端类型约束操作和审核结论，任务阶段接受字符串并通过只读映射返回中文；未知值返回“状态未知”。

- [x] **Step 4: 运行测试并确认通过**

Run: `npm exec --workspace @inkforge/web -- tsx --test src/features/workspace/__tests__/short-story-display-labels.test.ts`

Expected: PASS。

### Task 2: 接入中短篇工作区

**Files:**
- Modify: `apps/web/src/features/workspace/short-story/short-story-workspace.tsx`
- Modify: `apps/web/src/features/workspace/__tests__/short-story-api-source.test.ts`

- [x] **Step 1: 写组件源码失败测试**

断言组件不直接渲染任务操作、任务阶段和审核枚举，并且用户可见字符串中不再包含 `revision`。

- [x] **Step 2: 运行测试并确认失败**

Run: `npm exec --workspace @inkforge/web -- tsx --test src/features/workspace/__tests__/short-story-api-source.test.ts`

Expected: FAIL，命中当前英文直出位置。

- [x] **Step 3: 替换所有用户可见英文状态**

接入展示文案模块；保留英文枚举用于逻辑判断和 CSS 类名，将所有版本文案改为中文。

- [x] **Step 4: 运行测试并确认通过**

Run: `npm exec --workspace @inkforge/web -- tsx --test src/features/workspace/__tests__/short-story-api-source.test.ts src/features/workspace/__tests__/short-story-display-labels.test.ts`

Expected: PASS。

### Task 3: 完整验证

**Files:**
- Verify: `apps/web/src/features/workspace/short-story/short-story-display-labels.ts`
- Verify: `apps/web/src/features/workspace/short-story/short-story-workspace.tsx`

- [x] **Step 1: 运行完整前端测试**

Run: `npm run test:web`

Expected: 所有测试通过。

- [x] **Step 2: 运行静态检查**

Run: `npm run typecheck`，然后运行 `npm run lint`。

Expected: 两条命令退出码均为 0。

- [x] **Step 3: 真实页面验收**

打开 `http://localhost:43119/workspace/cmrr95evcqoirfnay34rzvuej`，确认顶部任务状态、审核结论和版本信息均为中文。
