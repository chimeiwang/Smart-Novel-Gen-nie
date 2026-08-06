# 设定库摘要列表视觉重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将设定库五类实体统一改造成层级清晰、整行可编辑、长文本仅视觉截断的摘要列表。

**Architecture:** 新增一个无 React 依赖的展示模型转换模块，集中把现有 API DTO 映射为统一摘要行数据；`LorePanel` 只负责渲染统一结构和触发现有编辑行为。设定库使用独立 CSS 类，避免继续受全局 `list-item-button` 覆盖链影响。

**Tech Stack:** Next.js 16、React 19、TypeScript、原生 CSS、Node.js Test Runner、tsx。

---

## 文件结构

- 新建 `apps/web/src/features/lore/lore-list-presenter.ts`：五类 DTO 到统一摘要行展示模型的纯函数映射。
- 新建 `apps/web/src/features/workspace/__tests__/lore-panel-list.test.ts`：展示模型、组件结构和 CSS 回归测试。
- 修改 `apps/web/src/features/lore/lore-panel.tsx`：使用统一展示模型渲染语义化摘要按钮。
- 修改 `apps/web/src/app/globals.css`：设定库摘要行、标签、截断、焦点和响应式样式。

### Task 1：建立展示模型契约

**Files:**
- Create: `apps/web/src/features/lore/lore-list-presenter.ts`
- Test: `apps/web/src/features/workspace/__tests__/lore-panel-list.test.ts`

- [x] **Step 1：先写五类字段映射的失败测试**

测试使用完整 DTO 固定数据，明确断言：

```ts
assert.deepEqual(buildLoreListItems("characters", fixtures), [{
  id: "character-1",
  kindLabel: "角色",
  name: "纪寻",
  initial: "纪",
  secondary: "玄天宗内门弟子",
  tags: [
    { label: "活跃", tone: "status" },
    { label: "玄天宗", tone: "neutral" },
    { label: "筑基中期", tone: "neutral" },
  ],
  summary: "会思考但不内耗",
  ariaLabel: "编辑角色：纪寻",
}]);
```

地点断言父地点名称和气候；势力断言总部地点；物品断言稀有度、持有者以及“效果优先、描述回退”；术语断言分类和定义。另写一个缺失可选字段测试，确保不生成空标签和推测值。

- [x] **Step 2：运行测试并确认因展示模块不存在而失败**

Run: `npx tsx --test apps/web/src/features/workspace/__tests__/lore-panel-list.test.ts`

Expected: FAIL，错误指向无法解析 `lore-list-presenter`，而不是测试语法错误。

- [x] **Step 3：实现最小纯函数展示模型**

实现以下公开契约：

```ts
export type LoreListKind = "characters" | "items" | "locations" | "factions" | "glossaries";

export type LoreListItemView = {
  id: string;
  kindLabel: "角色" | "物品" | "地点" | "势力" | "术语";
  name: string;
  initial: string;
  secondary: string | null;
  tags: Array<{ label: string; tone: "status" | "warning" | "neutral" }>;
  summary: string | null;
  ariaLabel: string;
};

export function buildLoreListItems(
  kind: LoreListKind,
  data: LoreListData,
): LoreListItemView[];
```

使用 `Map` 解析 `parentId` 和 `baseId`；只过滤空字符串和 `null`；人物摘要使用 `personality || statusNote`，物品摘要使用 `effect || description`。不裁剪任何文本。

- [x] **Step 4：运行展示模型测试并确认通过**

Run: `npx tsx --test apps/web/src/features/workspace/__tests__/lore-panel-list.test.ts`

Expected: PASS，字段映射与缺失字段测试全部通过。

### Task 2：替换列表 DOM 结构

**Files:**
- Modify: `apps/web/src/features/lore/lore-panel.tsx`
- Test: `apps/web/src/features/workspace/__tests__/lore-panel-list.test.ts`

- [x] **Step 1：先写组件结构失败测试**

读取 `lore-panel.tsx` 源码并断言：

```ts
assert.match(source, /buildLoreListItems/);
assert.match(source, /className="lore-summary-item"/);
assert.match(source, /aria-label=\{item\.ariaLabel\}/);
assert.match(source, /lore-summary-description/);
assert.doesNotMatch(source, /className="list-item list-item-button"/);
```

- [x] **Step 2：运行测试并确认旧结构导致失败**

Run: `npx tsx --test apps/web/src/features/workspace/__tests__/lore-panel-list.test.ts`

Expected: FAIL，缺少 `lore-summary-item`，并仍匹配旧的 `list-item list-item-button`。

- [x] **Step 3：用统一摘要行重写 `renderList()`**

在空状态判断之后调用 `buildLoreListItems(activeTab, data)`，统一渲染：

```tsx
<button className="lore-summary-item" aria-label={item.ariaLabel}>
  <span className="lore-summary-mark" aria-hidden="true">{item.initial}</span>
  <span className="lore-summary-heading">
    <strong className="lore-summary-name">{item.name}</strong>
    {item.secondary && <span className="lore-summary-secondary">{item.secondary}</span>}
  </span>
  <span className="lore-summary-content">
    {item.tags.length > 0 && <span className="lore-summary-tags">...</span>}
    {item.summary && <span className="lore-summary-description">{item.summary}</span>}
  </span>
  <span className="lore-summary-arrow" aria-hidden="true">›</span>
</button>
```

保留原 `openEditModal(item.id)`，不修改新增、编辑、删除和表单代码。

- [x] **Step 4：运行组件结构和展示模型测试并确认通过**

Run: `npx tsx --test apps/web/src/features/workspace/__tests__/lore-panel-list.test.ts`

Expected: PASS。

### Task 3：增加专用视觉样式并完成验证

**Files:**
- Modify: `apps/web/src/app/globals.css`
- Test: `apps/web/src/features/workspace/__tests__/lore-panel-list.test.ts`

- [x] **Step 1：先写 CSS 行为失败测试**

读取 `globals.css` 并断言存在：

```ts
assert.match(css, /\.lore-summary-item\s*\{/);
assert.match(css, /\.lore-summary-description\s*\{[\s\S]*?-webkit-line-clamp:\s*2/);
assert.match(css, /\.lore-summary-item:focus-visible/);
assert.match(css, /@container lore-panel \(max-width:\s*640px\)[\s\S]*?\.lore-summary-item/);
assert.match(css, /@media \(prefers-reduced-motion:\s*reduce\)/);
```

- [x] **Step 2：运行测试并确认专用样式不存在而失败**

Run: `npx tsx --test apps/web/src/features/workspace/__tests__/lore-panel-list.test.ts`

Expected: FAIL，缺少 `.lore-summary-item` 和两行截断规则。

- [x] **Step 3：实现摘要列表样式**

使用现有 `--panel`、`--panel-soft`、`--border`、`--text`、`--muted`、`--accent` 等变量实现：桌面四列网格、清晰边界与内边距、弱悬停态、可见焦点、状态标签、两行截断；设定面板容器宽度低于 `640px` 时把摘要区换到名称下方；减少动态偏好下取消位移。

- [x] **Step 4：运行定向测试并确认通过**

Run: `npx tsx --test apps/web/src/features/workspace/__tests__/lore-panel-list.test.ts`

Expected: PASS。

- [x] **Step 5：运行完整前端验证**

Run: `npm run test:web`

Expected: 所有 Web 与 API client 测试通过。

Run: `npm run typecheck`

Expected: TypeScript 类型检查通过。

Run: `npm run lint`

Expected: ESLint 通过且没有新增错误。

- [x] **Step 6：核对最终差异并提交实现**

Run: `git diff --check`

Expected: 无空白错误。只暂存本计划涉及的四个实现/测试文件和计划文档，不包含工作区原有无关改动。

Commit message: `前端：重构设定库摘要列表`
