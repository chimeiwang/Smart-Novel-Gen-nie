# InkForge（墨铸）项目结构与需求方案

## 1. 项目目标

InkForge（墨铸）是一款面向中文小说作者的本地优先智能创作工具。它结合传统写作工作台与 AI 辅助能力，帮助作者以更低的维护成本完成长篇创作，同时尽量保证设定一致、文风稳定、素材可检索、章节可管理。

本方案基于两份原始文档进行收敛，目标不是一次性覆盖全部商业想象，而是先搭出一个能尽快落地、能继续演进的产品骨架。

首要原则：

- 先把个人作者最常用的写作闭环跑通
- 先做本地优先，降低架构复杂度
- 先做可扩展的数据层和工作台框架，再逐步补 AI 深能力
- 先服务专业写作者和高频创作用户，再考虑协同生态

## 2. 产品定位

一句话定位：

基于 AI 的本地优先小说创作工作台，帮助作者管理小说、章节、设定、大纲、剧情进度、参考资料，并在既有文风和设定约束下完成智能续写。

### 2.1 核心用户

- 核心用户：网文作者、长篇小说作者、同人写作者
- 次级用户：轻度创作者、剧本爱好者、世界观构建型用户
- 长期用户：普通故事消费者转型为创作者的用户群体

### 2.2 核心价值

- 降低卡文成本
- 降低设定维护成本
- 降低长篇写作中的信息遗忘问题
- 保持文风统一
- 建立“小说级”知识资产，方便 AI 按上下文调用
- 为后续协同创作、设定交易、视觉化生成留下结构空间

## 3. 产品范围收敛

## 3.1 MVP 目标

首版只解决一件事：

让用户可以在一个本地工作台中，顺畅地完成“小说管理 → 章节创作 → 设定维护 → 大纲/剧情进度辅助 → AI 续写”这一主链路。

### 3.2 首期必须做

- 项目管理
- 章节管理
- Markdown 优先编辑器
- 自动保存
- 字数统计
- 设定管理
- 大纲管理
- 剧情进度管理
- 参考资料管理
- 文风管理
- 文风提取 Agent
- AI 续写服务抽象
- 全文搜索
- 数据库存储

### 3.3 首期预留但不深做

- 富文本编辑器能力
- 设定悬浮卡片
- 设定自动识别
- 地图视图与地点设定联动
- 多模型接入
- 导出 TXT / Markdown

### 3.4 后续阶段再做

- 角色关系图谱
- 时间轴系统
- 一致性检测
- 多 Agent 推演
- AI 主动提问
- 任意节点续写
- 投票驱动续写
- 平行宇宙分支
- 视频生成链路

## 4. 功能结构

## 4.1 工作台层级

```text
InkForge（墨铸）├── 项目列表页
├── 文风库页
└── 创作工作台
    ├── 左侧：以 Tab 切换章节 / 设定
    ├── 中间：章节编辑区 / Markdown 预览 / AI 操作区
    └── 右侧：以 Tab 切换大纲 / 剧情进度 / 文风 / 参考资料
```

## 4.2 首期模块拆分

### A. 项目与章节

- 创建项目
- 切换项目
- 默认创建第一章
- 章节新增、删除、重命名
- 章节排序调整
- 当前章节高亮
- 章节字数与全文字数统计

### B. 编辑器

- Markdown 编辑模式
- 预览模式
- 自动保存
- 保存状态提示
- 光标位置插入 AI 生成内容

### C. 设定库

- 分类：角色、物品、名词解释、其他
- 基础字段：名称、分类、描述
- 增删改查
- 在左侧 Tab 中集中查看与管理
- 新增和编辑通过弹窗完成，列表本身保持简洁

### D. 大纲

- 一个小说对应一个大纲
- 大纲下包含多个节点
- 节点支持标题、摘要、排序、关联章节
- 支持跳转到对应章节

### E. 剧情进度

- 记录当前推进到哪个剧情阶段
- 支持里程碑、当前冲突、下一步目标
- 作为 AI 续写的重要上下文来源

### F. 文风与 AI

- 文风作为独立资源管理
- 文风提取在独立“文风库”页面中进行
- 支持从一段文本中提取文风特征
- 文风提取由单独 Agent 完成
- 每本小说内只负责选择和应用文风
- AI 续写参数：短 / 中 / 长
- AI Prompt 组装层
- AI 结果接受 / 重试

### G. 参考资料与搜索

- 参考资料支持标题、类型、内容、来源链接
- 可作为 AI 检索上下文
- 全文搜索章节内容
- 搜索结果跳转

## 5. 用户主流程

## 5.1 新建项目

1. 进入项目列表页
2. 创建项目
3. 系统初始化默认数据
4. 自动进入工作台并打开第一章

## 5.2 写作流程

1. 用户选择章节
2. 在编辑器中输入内容
3. 系统自动保存
4. 左侧通过 Tab 切换章节与设定，右侧通过 Tab 切换大纲、剧情进度、文风、参考资料
5. 需要时插入设定名或发起 AI 续写

## 5.3 AI 续写流程

1. 获取当前光标上下文或选中文本
2. 提取当前章节内容片段
3. 匹配可能相关的角色、地点、物品设定
4. 读取小说大纲与当前剧情进度
5. 读取小说应用的文风配置
6. 检索相关参考资料
7. 组装 Prompt
8. 调用模型
9. 将生成结果显示为候选内容
10. 用户选择接受、重试或手动修改

## 6. 非功能要求

- 本地优先：数据默认存于本地数据库
- 离线可读写：除 AI 续写外，其余功能均可离线使用
- 响应速度：章节切换、搜索、面板切换应尽量控制在 1 秒以内
- 可扩展：数据结构支持未来增加地图、时间轴、关系图谱、平行宇宙分支
- 隐私：用户数据不上传，模型密钥通过环境变量注入

## 7. 技术方案

## 7.1 技术栈选择

结合“实现要快”和你当前的选择，首版采用：

- Next.js
- TypeScript
- App Router
- Prisma
- SQLite
- React Markdown 或同类方案承接首版 Markdown 预览
- dnd-kit 负责章节与大纲节点的拖拽排序

选择这个组合的原因：

- Next.js 的工程组织能力强，后续加路由、设置页、导出页更自然
- 仍可作为本地 Web 工具使用
- TypeScript 适合先把领域模型立稳
- SQLite 更接近真正的数据层，后续做检索、导出、迁移更自然
- Prisma 适合快速建模和迭代

## 7.2 总体架构

```text
src
├── app
│   ├── page.tsx
│   ├── projects
│   ├── workspace
│   └── settings
├── features
│   ├── projects
│   ├── chapters
│   ├── editor
│   ├── lore
│   ├── outline
│   ├── progress
│   ├── references
│   ├── styles
│   ├── ai
│   ├── search
│   └── agents
├── entities
│   ├── novel
│   ├── chapter
│   ├── lore-entry
│   ├── outline
│   ├── outline-node
│   ├── plot-progress
│   ├── reference-material
│   └── writing-style
├── shared
│   ├── db
│   ├── env
│   ├── lib
│   ├── ui
│   └── types
└── widgets
    ├── shell
    ├── sidebar
    ├── editor-pane
    └── inspector-pane
```

## 7.3 页面结构

### 首页

- 项目列表
- 新建项目弹窗
- 最近编辑项目

### 工作台页

- 左栏：项目名、章节树、搜索
- 中栏：编辑器、字数、保存状态、AI 操作条
- 右栏：设定、大纲、剧情进度、文风、参考资料切换面板

### 设置页

- AI 提供商配置
- 模型信息展示
- 默认续写长度
- 风格模板管理
- 环境变量检测结果

## 8. 领域模型

## 8.1 Novel

```ts
type Novel = {
  id: string
  name: string
  summary?: string
  appliedStyleId?: string
  createdAt: string
  updatedAt: string
}
```

## 8.2 Chapter

```ts
type Chapter = {
  id: string
  novelId: string
  title: string
  content: string
  order: number
  createdAt: string
  updatedAt: string
}
```

## 8.3 LoreEntry

```ts
type LoreCategory = 'character' | 'item' | 'glossary' | 'other'

type LoreEntry = {
  id: string
  novelId: string
  category: LoreCategory
  name: string
  description: string
  aliases?: string[]
  createdAt: string
  updatedAt: string
}
```

## 8.4 Outline

```ts
type Outline = {
  id: string
  novelId: string
  title: string
  summary?: string
  createdAt: string
  updatedAt: string
}
```

## 8.5 OutlineNode

```ts
type OutlineNode = {
  id: string
  outlineId: string
  parentId?: string
  title: string
  summary: string
  linkedChapterId?: string
  order: number
}
```

## 8.6 PlotProgress

```ts
type PlotProgress = {
  id: string
  novelId: string
  currentStage: string
  currentGoal?: string
  currentConflict?: string
  nextMilestone?: string
  updatedAt: string
}
```

## 8.7 ReferenceMaterial

```ts
type ReferenceMaterial = {
  id: string
  novelId: string
  title: string
  type: 'note' | 'web' | 'book' | 'image' | 'custom'
  content: string
  sourceUrl?: string
  createdAt: string
  updatedAt: string
}
```

## 8.8 WritingStyle

```ts
type WritingStyle = {
  id: string
  name: string
  sampleText: string
  extractedProfile: string
  sourceType: 'manual' | 'agent'
  createdAt: string
  updatedAt: string
}
```

## 8.9 StyleExtractionTask

```ts
type StyleExtractionTask = {
  id: string
  styleId: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  sourceText: string
  result?: string
  errorMessage?: string
  createdAt: string
  updatedAt: string
}
```

## 9. 本地存储设计

## 9.1 SQLite 表

- novels
- chapters
- loreEntries
- outlines
- outlineNodes
- plotProgresses
- referenceMaterials
- writingStyles
- styleExtractionTasks

## 9.2 存储原则

- 所有业务数据按 novelId 分组
- 章节内容单独表存储，避免小说对象过大
- 更新时间字段统一存在，便于排序和同步导出
- 后续可增加 snapshots 表支持历史版本和撤销恢复
- 风格抽取任务单独落表，方便后续接异步 Agent

## 10. AI 架构预留

## 10.1 AI 接入目标

首期按 OpenAI 兼容协议实现，默认接 DeepSeek。模型配置通过 `.env` 注入，后续再扩展更多提供商。

## 10.2 AI 服务分层

```text
AIProviderAdapter
├── buildPrompt(context)
├── extractStyle(sampleText)
├── generateContinuation(params)
└── normalizeResponse(result)
```

## 10.3 Prompt 输入来源

- 用户选中的文本或光标附近文本
- 当前章节最近上下文
- 当前小说应用的文风画像
- 相关设定
- 大纲摘要
- 当前剧情进度
- 命中的参考资料

## 10.4 环境变量约定

```env
OPENAI_API_KEY=your_deepseek_api_key
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=ddeepseek-v4-flash
```

## 11. 首批要搭的基础架构

这部分是确认后立即编码的内容。

### 11.1 工程脚手架

- Next.js + TypeScript 初始化
- 基础路由
- 全局样式
- 通用布局壳

### 11.2 领域层

- 核心 TypeScript 类型
- 默认枚举与常量
- 小说初始化工厂函数

### 11.3 数据层

- Prisma Schema 定义
- Repository 封装
- 基础 CRUD 方法

### 11.4 状态层

- 当前小说状态
- 当前章节状态
- 工作台面板状态
- 自动保存状态
- 基于服务端数据和本地组件状态驱动，不引入 Zustand

### 11.5 UI 骨架

- 项目列表页
- 工作台三栏布局
- 左侧章节 / 设定 Tab 骨架
- 编辑器占位
- 右侧大纲 / 剧情进度 / 文风 / 参考资料面板切换骨架

### 11.6 AI 预留层

- OpenAI 兼容 Provider 配置结构
- Prompt 组装器接口
- 文风提取 Agent 接口
- 续写调用入口
- Mock 返回结果，先打通交互链路

## 12. 首个迭代建议

为了尽快出东西，建议第一轮编码只完成下面 4 个目标：

1. 可以新建项目并自动创建第一章
2. 可以在工作台切换章节并编辑 Markdown
3. 可以维护设定、大纲、剧情进度、参考资料的基础数据
4. 可以点击“AI 续写”与“提取文风”后走通一个可替换的 Mock 流程

这样做的价值是：

- 能最快验证产品主流程
- 数据层和 UI 框架不会返工太多
- 后续加富文本、搜索、导出和真实 AI 接口都比较顺滑

## 13. 编码前确认项

如果按当前方案推进，我下一步会直接开始：

- 初始化 Next.js 工程
- 建立 src 分层目录
- 搭建数据模型与 SQLite 数据库
- 做项目列表页和工作台三栏骨架
- 接入 Markdown 编辑主链路
- 预留 AI 续写与文风提取服务接口

当前默认采用的确认结果：

- 技术栈：Next.js
- 数据层：Prisma + SQLite
- 编辑器策略：Markdown 优先
- 状态管理：不引入 Zustand
- 模型接入：`.env` 中使用 OpenAI 兼容配置，默认接 DeepSeek
- 首批范围：小说工作台四件套 + 文风提取接口

你确认后，我就按这份文档直接开工搭第一版基础架构。

## 14. 执行计划与进度标记

为了避免上下文过长或中途中断，后续我会把实际推进情况直接更新在这一节。规则如下：

- 每完成一个阶段，就把对应项从 `[ ]` 改成 `[x]`
- 每次标记时补一条“最近完成”
- 如果还没开始，会明确写“未开始”
- 这样即使对话中断，你也能直接打开这个文件看到推进到哪一步

### 14.1 当前进度总览

- 最近完成：设定迁移到左侧 Tab，并重构为角色 / 物品 / 名词解释 / 其他四类
- 当前状态：界面结构已按最新产品要求再次调整，待完成本轮验证
- 下一步：完成 lint / typecheck / build 验证并继续补删除、排序等交互

### 14.2 分阶段执行清单

- [x] 阶段 0：完成需求收敛与技术选型
- [x] 阶段 1：完成核心数据结构设计
- [x] 阶段 2：初始化 Next.js 工程
- [x] 阶段 3：接入 Prisma 与 SQLite
- [x] 阶段 4：落库核心表结构
- [x] 阶段 5：搭建小说列表页
- [x] 阶段 6：搭建工作台三栏布局
- [x] 阶段 7：接入章节编辑主链路
- [x] 阶段 8：接入设定 / 大纲 / 剧情进度 / 参考资料基础 CRUD
- [x] 阶段 9：接入文风管理与文风提取接口
- [x] 阶段 10：接入 AI 续写服务层
- [x] 阶段 11：基础验证与整理

### 14.3 每阶段交付物

#### 阶段 0：需求收敛与技术选型

- 输出统一方案文档
- 明确技术栈为 Next.js + Prisma + SQLite
- 明确模型接入为 `.env` + OpenAI 兼容格式 + DeepSeek

#### 阶段 1：核心数据结构设计

- 定义 Novel
- 定义 Chapter
- 定义 LoreEntry
- 定义 Outline / OutlineNode
- 定义 PlotProgress
- 定义 ReferenceMaterial
- 定义 WritingStyle / StyleExtractionTask

#### 阶段 2：初始化 Next.js 工程

- 创建基础工程
- 建立 `src` 分层目录
- 配置基础样式与页面骨架

#### 阶段 3：接入 Prisma 与 SQLite

- 初始化 Prisma
- 创建 SQLite 数据库文件
- 配置数据库连接

#### 阶段 4：落库核心表结构

- 编写 Prisma Schema
- 生成迁移
- 生成 Prisma Client

#### 阶段 5：搭建小说列表页

- 小说列表展示
- 新建小说入口
- 点击进入工作台

#### 阶段 6：搭建工作台三栏布局

- 左栏章节区
- 中栏编辑区
- 右栏信息面板区

#### 阶段 7：接入章节编辑主链路

- 章节切换
- Markdown 编辑
- 自动保存
- 字数统计

#### 阶段 8：接入基础 CRUD

- 设定管理
- 大纲管理
- 剧情进度管理
- 参考资料管理

#### 阶段 9：接入文风管理与提取

- 文风列表
- 文风详情
- 从样本文本提取文风
- 小说绑定文风

#### 阶段 10：接入 AI 续写服务层

- DeepSeek 兼容配置读取
- Prompt 组装
- 续写接口封装
- Mock 与真实接口切换

#### 阶段 11：基础验证与整理

- 检查工程能否运行
- 检查数据库迁移是否正常
- 检查基础页面和主链路是否可用

### 14.4 进度记录

- [x] 记录 1：已完成需求与数据结构文档整理，代码尚未开始
- [x] 记录 2：已完成工程初始化、数据库建模、首页与工作台骨架、基础 CRUD、文风提取与 AI 续写骨架，正在进入验证阶段
- [x] 记录 3：已完成 lint、typecheck、build 验证，首版基础架构当前可运行
- [x] 记录 4：已将小说页右侧栏改为 Tab 切换，并把文风提取拆到独立文风库页面，小说内仅保留文风选择
- [x] 记录 5：已将设定迁移到左侧 Tab，并把设定分类改为角色、物品、名词解释、其他，同时同步数据库字段
- [x] 记录 6：已将设定调整为列表视图，新增与编辑统一改为弹窗交互，每条设定都可点击进入编辑
