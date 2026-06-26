---
version: alpha
name: InkForge-Linear-first-product-design
description: "InkForge（墨铸）的目标设计规范。主参考 Linear 的产品型工作台：信息密度适中、层级清楚、侧栏/任务流/检查器稳定、装饰克制；辅助参考 Vercel 的控件精度：hairline 边框、干净按钮、输入框、空状态和开发者工具感。当前实现只作为迁移约束，不是视觉上限。"
inspiration:
  primary: "Linear"
  secondary: "Vercel"
  avoid:
    - "Notion as primary system"
    - "Stripe / Apple / Airbnb marketing-page language"
    - "large dark marketing hero"
    - "large saturated gradient"
    - "decorative consumer-app chrome"
principles:
  density: "Linear-like focused density; compact but readable."
  structure: "Workspace shell first: sidebar, main canvas, inspector, status stream."
  surface: "Quiet product surfaces; use borders and separation before decoration."
  writing: "Long-form writing comfort is non-negotiable."
  agent: "Agent activity is visible but not theatrical."
colors:
  app-bg: "#f6f4ef"
  app-bg-subtle: "#fbfaf7"
  sidebar-bg: "#f7f5f0"
  sidebar-active: "#ffffff"
  surface: "#ffffff"
  surface-raised: "#ffffff"
  surface-subtle: "#f1eee7"
  surface-inset: "#ebe7dd"
  border: "#e4ded2"
  border-strong: "#d6ccbb"
  divider: "#ebe5d9"
  text: "#1f2328"
  text-secondary: "#4f565f"
  text-muted: "#767d86"
  text-subtle: "#9a9fa6"
  primary: "#252a31"
  primary-hover: "#111418"
  primary-soft: "#ebe7dd"
  focus-ring: "rgba(37, 42, 49, 0.16)"
  link: "#34495e"
  success: "#16a34a"
  success-soft: "#eaf8ef"
  warning: "#d97706"
  warning-soft: "#fff4df"
  danger: "#dc2626"
  danger-soft: "#fff0f0"
  info: "#2563eb"
  info-soft: "#eaf1ff"
  agent-lore: "#7c3aed"
  agent-plot: "#2563eb"
  agent-author: "#16a34a"
  agent-validator: "#d97706"
  agent-editor: "#dc2626"
typography:
  display:
    fontFamily: "Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, PingFang SC, Microsoft YaHei, Helvetica Neue, sans-serif"
    fontSize: 24px
    fontWeight: 650
    lineHeight: 32px
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, PingFang SC, Microsoft YaHei, Helvetica Neue, sans-serif"
    fontSize: 18px
    fontWeight: 650
    lineHeight: 26px
    letterSpacing: "-0.01em"
  panel-title:
    fontFamily: "Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, PingFang SC, Microsoft YaHei, Helvetica Neue, sans-serif"
    fontSize: 15px
    fontWeight: 600
    lineHeight: 22px
    letterSpacing: 0
  body:
    fontFamily: "Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, PingFang SC, Microsoft YaHei, Helvetica Neue, sans-serif"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 22px
    letterSpacing: 0
  writing-body:
    fontFamily: "Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, PingFang SC, Microsoft YaHei, Helvetica Neue, sans-serif"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 28px
    letterSpacing: 0
  compact:
    fontFamily: "Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, PingFang SC, Microsoft YaHei, Helvetica Neue, sans-serif"
    fontSize: 13px
    fontWeight: 400
    lineHeight: 18px
    letterSpacing: 0
  caption:
    fontFamily: "Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, PingFang SC, Microsoft YaHei, Helvetica Neue, sans-serif"
    fontSize: 12px
    fontWeight: 500
    lineHeight: 16px
    letterSpacing: 0
  mono:
    fontFamily: "Geist Mono, JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 18px
    letterSpacing: 0
rounded:
  xs: 4px
  sm: 6px
  md: 8px
  lg: 10px
  xl: 12px
  pill: 999px
spacing:
  1: 4px
  2: 8px
  3: 12px
  4: 16px
  5: 20px
  6: 24px
  8: 32px
  10: 40px
  12: 48px
elevation:
  hairline: "0 0 0 1px rgba(23, 25, 35, 0.06)"
  panel: "0 1px 2px rgba(23, 25, 35, 0.04)"
  popover: "0 8px 24px rgba(23, 25, 35, 0.10)"
  modal: "0 18px 48px rgba(23, 25, 35, 0.16)"
components:
  app-shell:
    backgroundColor: "{colors.app-bg}"
    textColor: "{colors.text}"
    layout: "sidebar + main canvas + right inspector"
  sidebar:
    backgroundColor: "{colors.sidebar-bg}"
    borderColor: "{colors.border}"
    activeBackground: "{colors.sidebar-active}"
    activeTextColor: "{colors.text}"
    typography: "{typography.compact}"
  workspace-panel:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.border}"
    textColor: "{colors.text}"
    rounded: "{rounded.lg}"
    shadow: "{elevation.panel}"
  inspector-panel:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.border}"
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.lg}"
    shadow: "{elevation.hairline}"
  button-primary:
    backgroundColor: "{colors.primary}"
    hoverBackgroundColor: "{colors.primary-hover}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    height: 34px
    padding: "0 {spacing.3}"
    typography: "{typography.compact}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    hoverBackgroundColor: "{colors.surface-subtle}"
    borderColor: "{colors.border}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    height: 34px
    padding: "0 {spacing.3}"
    typography: "{typography.compact}"
  button-ghost:
    backgroundColor: "transparent"
    hoverBackgroundColor: "{colors.surface-subtle}"
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.md}"
    height: 32px
    padding: "0 {spacing.2}"
    typography: "{typography.compact}"
  input:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.border}"
    focusBorderColor: "{colors.primary}"
    focusShadow: "0 0 0 3px {colors.focus-ring}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    height: 36px
    typography: "{typography.body}"
  writing-editor:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.border}"
    textColor: "{colors.text}"
    rounded: "{rounded.lg}"
    typography: "{typography.writing-body}"
    padding: "{spacing.6}"
  badge:
    backgroundColor: "{colors.surface-subtle}"
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.pill}"
    padding: "2px 8px"
    typography: "{typography.caption}"
  agent-status:
    backgroundColor: "{colors.surface-subtle}"
    borderColor: "{colors.border}"
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.md}"
    typography: "{typography.compact}"
  tool-log:
    backgroundColor: "{colors.surface-inset}"
    borderColor: "{colors.border}"
    textColor: "{colors.text-muted}"
    rounded: "{rounded.md}"
    typography: "{typography.mono}"
---

# InkForge（墨铸）Design System

## Overview

InkForge（墨铸）的目标界面不是“当前样式的文档化”，而是一次明确的产品设计方向定义：**以 Linear 为主参考，少量借 Vercel 的控件精度**。

InkForge（墨铸）是长时间使用的中文小说创作工作台。它要同时承载章节编辑、结构化大纲、设定管理、文风画像、AI 写作会话、质量检查、待审核草案和多 Agent 协作。因此它更接近 Linear 这种任务型生产力工具，而不是 Notion 式文档容器，也不是 Stripe / Apple / Airbnb 式品牌展示页面。

设计关键词：

- Linear-like product workspace
- Focused density
- Clear hierarchy
- Quiet confidence
- Fast operational feedback
- Comfortable long-form writing
- Agent activity without theater

中文落地语气：

- 清楚
- 克制
- 专注
- 利落
- 有秩序
- 长时间写作不累

## Inspiration Model

### Primary: Linear

Linear 是主参考。借鉴方向：

- 整体工作台结构：左侧导航、中央任务/内容区、右侧详情或检查器。
- 信息密度：控件紧凑但不拥挤，适合频繁操作。
- 视觉层级：靠边框、分隔线、轻背景和状态点建立层级，而不是靠大阴影。
- 任务流表达：状态、进度、审核、待办、错误都应该快速可扫。
- Agent 协作表达：Agent 像工作流里的参与者，不像聊天玩具或营销机器人。

不照搬：

- 不采用 Linear 官网的大面积深色营销氛围。
- 不把英文 SaaS 的冷感原封不动搬到中文写作场景。
- 不为了“像 Linear”牺牲正文阅读舒适度。

### Secondary: Vercel

Vercel 是辅助参考。借鉴方向：

- hairline 边框和干净的控件边界。
- 按钮、输入框、弹窗、空状态的精确尺寸。
- 技术日志、工具调用、调试信息的 mono 层级。
- 开发者工具感：清楚、快、没有多余装饰。

不照搬：

- 不采用 Vercel 官网式黑白极简营销气质。
- 不使用大面积 hero、mesh gradient、超大标题。
- 不把写作工作台做成部署平台页面。

### Avoid as Primary

Notion 不作为主参考。它适合块状文档编辑，但 InkForge（墨铸）有章节编辑、结构化大纲、Agent 工作流、审核草案，整套用 Notion 会显得松散。

Stripe / Apple / Airbnb 不作为主参考。它们更偏营销页、品牌展示或消费级体验，会让 InkForge（墨铸）变得过于展示型，不利于长时间写作和复杂工作流操作。

## Product Personality

InkForge（墨铸）的界面应该像一个专业写作控制台，不是灵感贴纸墙，也不是官网 landing page。

它应当让用户感觉：

- 我的稿件和设定是稳定可控的。
- Agent 正在严肃地参与创作流程。
- 每个草案、审核、应用和拒绝都有明确状态。
- 长文本编辑区安静、不抢戏。
- 工具日志存在，但默认不会干扰写作。

## Colors

目标色彩系统以 Linear 式的冷静结构为底，但不使用明显的 SaaS 彩色主色。InkForge（墨铸）是小说写作和 Agent 聊天工作台，主色应接近墨色 / 石墨黑：让按钮和焦点清楚，但不抢正文。页面底色可以轻微偏暖，像纸张和桌面，而不是冷冰冰的后台系统。状态色只做小面积语义提示。

### Application Surfaces

- `{colors.app-bg}` `#f6f4ef`：应用外层背景，轻微纸感，比纯白更适合写作。
- `{colors.app-bg-subtle}` `#fbfaf7`：大块空白或阅读背景。
- `{colors.sidebar-bg}` `#f7f5f0`：侧栏和导航区域。
- `{colors.surface}` `#ffffff`：主面板、输入区、编辑区。
- `{colors.surface-subtle}` `#f3f4f7`：hover、次级区域、浅底状态。
- `{colors.surface-inset}` `#eef0f5`：日志、嵌入式工具结果、调试区域。

### Borders & Dividers

- `{colors.border}` `#e5e7ef`：默认边框。
- `{colors.border-strong}` `#d5d8e3`：选中项、当前项、重要分隔。
- `{colors.divider}` `#eceef5`：表格行、列表行、面板内部分隔。

### Text

- `{colors.text}` `#171923`：主标题和正文。
- `{colors.text-secondary}` `#4b5565`：次级标题、面板说明。
- `{colors.text-muted}` `#778092`：元信息、时间、备注。
- `{colors.text-subtle}` `#9aa3b5`：占位符、空状态弱说明。

### Accent & Semantic

- `{colors.primary}` `#252a31`：主操作、当前导航、焦点、重要进度。它应表现为墨色 / 石墨黑，不要偏紫、偏蓝或偏绿。
- `{colors.primary-soft}` `#ebe7dd`：选中背景、轻量信息提示，带一点纸感。
- `{colors.success}`：已完成、已应用、通过。
- `{colors.warning}`：待审核、进行中、需注意。
- `{colors.danger}`：错误、删除、失败、阻断。
- Agent 类型色只能小面积使用，不能把整个页面染成 Agent 颜色。

## Typography

字体以 Inter + 中文系统字体为主，保持工具感。不要为了“设计感”引入会影响中文正文阅读的展示字体。

规则：

- 页面标题最多 24px，避免营销页式 hero 大标题。
- 面板标题 15px 到 16px，字重 600。
- 工具列表、状态行、按钮可以使用 12px 到 13px 的紧凑字号。
- 正文和 Agent 回复用 14px 到 15px。
- 章节正文编辑器目标为 16px / 28px 左右，优先保护长时间阅读和输入。
- `mono` 只用于工具调用、日志、代码、ID、调试字段。
- 中文正文不使用负字距；英文 UI 小标题可以轻微收紧，但必须可读。

## Layout

InkForge（墨铸）的主布局应走 Linear 式工作台结构：

```text
App Shell
├── Sidebar: 小说、章节、设定、大纲、文风入口
├── Main Canvas: 当前章节、写作任务、草案审核
├── Inspector: 设定、大纲、质量检查、Agent 状态
└── Composer / Status: AI 输入、流式状态、工具调用摘要
```

布局原则：

- PC 优先，不默认新增移动端响应式方案。
- 使用稳定的 sidebar / main / inspector 三栏模型。
- 主写作区比辅助区更安静、更宽松。
- 列表和审核区可以更高密度，保持快速扫描。
- 操作区靠近上下文，不做漂浮的营销式 CTA。
- 面板之间优先用 1px border、浅底和留白分隔。

推荐尺寸：

- 页面外层 padding：12px 到 16px。
- 面板间距：8px 到 12px。
- 工具栏高度：36px 到 44px。
- 列表项高度：32px 到 40px。
- 按钮高度：32px 到 36px。
- 写作正文区 padding：20px 到 28px。

## Components

### App Shell

App Shell 是主角。不要为每个功能单独发明页面风格。

- 左侧导航应稳定、紧凑，当前项用轻背景 + 左侧细线或状态点表达。
- 主区承载当前写作任务，避免太多浮层和嵌套卡片。
- 右侧检查器用于设定、大纲、质量、Agent 状态，信息密度可略高。
- 顶部栏只放当前上下文和必要操作，不放营销文案。

### Panels

Panel 应接近 Linear 的产品面板：

- 轻边框，低阴影或无阴影。
- header 清楚，body 紧凑，footer 只放必要操作。
- 不做大圆角卡片群。
- 不做卡片套卡片，除非内部是明确的重复列表项。
- 可滚动区域边界要明确，不能让文本贴边。

### Buttons

按钮借 Vercel 的精确和 Linear 的克制：

- Primary 用于当前上下文唯一主动作。
- Secondary 用于普通保存、切换、提交。
- Ghost 用于低优先级操作、折叠、展开、查看详情。
- Danger 必须文字明确，不只靠红色。
- 图标按钮必须有 `title` 或可访问名称。
- hover、focus、disabled、loading 都必须有状态。

### Inputs

- 输入框边框要清楚，focus 使用 `{colors.primary}` 和轻 focus ring。
- 文本域不要强阴影。
- 章节正文编辑器仍使用 `textarea`，但视觉目标应更接近安静写作画布。
- 搜索、筛选、短输入可以更紧凑，正文输入必须留足行高。

### Lists & Tables

Linear 式密度主要体现在列表：

- 行高稳定，hover 不导致布局跳动。
- 当前项、选中项、待审核项必须能快速扫出来。
- 状态用小圆点、badge、轻背景即可，不做大色块。
- 列表操作默认低调，hover 或选中后再显露。

### Badges & Status

- Badge 是信息标签，不是装饰。
- 状态必须同时有文字和颜色。
- 待审核、已应用、已拒绝、失败、处理中要有稳定语义。
- Agent 类型色只用于小圆点、边线、badge，不做整块背景。

### Writing Editor

写作区不完全照 Linear，因为它承担长文本创作。

- 字号和行高比普通工具区更宽松。
- 保留安静白色或近白色编辑画布。
- 自动保存、字数、章节状态应靠近编辑上下文，但不能抢正文注意力。
- 编辑器周边的 Agent 建议、质量问题、草案提示应可折叠或分区。

### Agent Conversation

Agent 会话应像工作流，不像社交聊天。

必须区分：

1. 用户和 Agent 的可读消息。
2. Agent 当前状态：理解请求、思考中、调用工具、输出回复、整理结果、完成、出错。
3. 工具调用日志和调试信息。

展示规则：

- 聊天气泡只显示用户关心的正文。
- 工具调用默认只展示工具名和简短参数摘要。
- 工具返回内容默认隐藏，不进入聊天气泡。
- 详细结果放在可折叠日志、调试抽屉或开发模式。
- Agent 状态用轻量行、badge、progress marker，不做大型动画。
- 当前 Agent 聊天正文按普通段落文本渲染，不使用 ReactMarkdown 解析。

### Review Artifacts

待审核草案是 InkForge（墨铸）的核心业务界面，应使用 Linear 式任务流表达：

- 草案状态必须显眼但克制。
- 应用、拒绝、要求返工是明确操作，不做模糊 CTA。
- diff、变更摘要、评审结果应结构化呈现。
- 大纲节点、设定变更、正文草案要能快速区分。
- 不把待审核草案伪装成正式正文。

## Motion

动效服务反馈，不制造气氛。

允许：

- hover 背景变化。
- focus ring。
- 1px 到 2px 的轻位移。
- 折叠区域轻量展开。
- 流式状态的细微 progress pulse。

避免：

- 大幅弹跳。
- 无限旋转装饰。
- 页面级复杂转场。
- 大面积发光、粒子、渐变动画。
- Agent 状态的戏剧化动画。

推荐 transition：

```css
transition:
  background-color 120ms ease,
  border-color 120ms ease,
  color 120ms ease,
  box-shadow 120ms ease,
  transform 120ms ease;
```

## Implementation Rules

- 新增或修改 UI、CSS、交互状态前，必须先阅读本文件。
- 本文件是前端设计主规范；不是当前界面的样式快照。
- `src/app/globals.css` 是当前落地点，但可以按本文件逐步迁移。
- 使用原生 CSS 和 CSS 自定义属性，不引入 Tailwind。
- 优先复用 `.panel`、`.stack`、`.row`、`.button`、`.badge`、`.input`、`.textarea`、`.select` 等基础类；如果基础类不符合本文件，应小步更新基础类，而不是局部堆覆盖。
- 新增类名要语义化，不按颜色或视觉命名。
- 不写移动端 media query，除非需求明确改变 PC 优先策略。
- 不使用全局选择器强行覆盖大范围样式。
- 避免重复定义相近颜色；能抽为变量时优先抽变量。
- Ant Design 可作为依赖使用，但新增 UI 不应呈现 Ant Design 默认视觉。

## Migration Guidance

当前项目已有浅色、低阴影、小圆角、蓝色主操作的基础。后续前端改动应逐步向本文件迁移：

- 把普通蓝色、偏紫或偏青主操作逐步收敛到 `{colors.primary}` 这类墨色主操作；彩色只作为状态提示小面积使用。
- 把过大的圆角、厚阴影、漂浮卡片改为 hairline + 低阴影。
- 把工具日志和 Agent 调试信息从聊天正文中分离。
- 把面板布局收敛到稳定的 app shell / main canvas / inspector 模型。
- 把状态表达从大色块改为小面积 badge、状态点、边线和轻背景。
- 保留正文编辑器的舒适行高，不为了高密度牺牲写作体验。

## Do's and Don'ts

### Do

- 以 Linear 的产品工作台作为整体方向。
- 借 Vercel 的控件边界、输入框、按钮和空状态精度。
- 使用紧凑但可读的信息密度。
- 用边框、浅底、状态点和小 badge 建立层级。
- 让写作正文区比管理区更安静。
- 让草案审核、Agent 状态、质量问题像任务流一样清楚。
- 每次前端实现前先读本文件，并说明如何遵循。

### Don't

- 不要继续只按旧界面惯性补样式。
- 不要把 InkForge（墨铸）做成营销页。
- 不要用 Notion 作为整体风格主参考。
- 不要使用 Stripe / Apple / Airbnb 式大展示页面语言。
- 不要大面积深色背景或高饱和渐变。
- 不要过度卡片化或卡片套卡片。
- 不要把工具调用完整结果塞进聊天气泡。
- 不要为了视觉统一牺牲中文长文本阅读。

## Acceptance Checklist

- 是否明确遵循 Linear 主参考、Vercel 辅助细节。
- 是否比当前样式更像稳定的产品工作台，而不是旧样式搬运。
- 是否保持长时间写作舒适。
- 是否避免营销页、强装饰、过度卡片和大面积深色。
- 主次信息是否清楚。
- 状态是否有文字和颜色双重表达。
- 文本是否没有溢出、重叠或被遮挡。
- 工具调用详情是否默认隐藏。
- 是否复用了或合理升级了基础样式 token。
- 是否通过 `npm run typecheck`，必要时运行 `npm run lint`。
