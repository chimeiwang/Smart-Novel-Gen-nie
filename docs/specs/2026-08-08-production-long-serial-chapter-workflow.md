# 生产长篇连续章节工作流与章节创建 CLI

## 状态

已实现并通过验证。

## 背景

生产长篇操作 Skill 已能查询章节、规划章节、生成正文、审核正文和处理 ReviewArtifact，但 CLI 未暴露
Core 已有的章节创建公共接口。结果是：当用户要求连续创作多个尚不存在的章节时，操作员无法通过既有
公共 CLI 建立后续章节，只能停止，或错误地尝试绕过 CLI。

同时，现有长篇 Skill 主要罗列命令与单章闭环，没有明确多章连续创作的准备门禁、顺序、停止条件、
Artifact 决策边界和小修改返工路线，难以稳定指导完整生产操作。

## 目标

1. 在 InkForge CLI 增加 `long.chapter.create`，只调用已有公共接口
   `POST /api/v1/novels/{novelId}/chapters`。
2. 将该命令加入生产 wrapper 的精确 allowlist 和能力计数。
3. 补全生产长篇 Skill 的端到端工作流，使其能稳定处理单章和连续多章创作。
4. 保持正式正文变更经过 `proposal -> ReviewArtifact -> 用户独立决策 -> Core 应用`。

## 非目标

- 不修改 Core API、PostgreSQL schema、数据库访问代码或 Web UI。
- 不允许 CLI 指定新章节标题、序号、正文或状态；这些仍由 Core 现有创建语义决定。
- 不开放大纲节点、伏笔或用户级文风资产写入。
- 不把长篇 Artifact 决策纳入中短篇 automatic 授权。
- 不让操作员在作品缺少足够规划时自行补写未经用户批准的全书大纲。

## CLI 契约

### 输入

`long.chapter.create` 使用 JSON 输入：

```json
{
  "novelId": "novel-id",
  "profile": "production"
}
```

`novelId` 必须是非空字符串。`profile` 由现有 CLI runtime/wrapper 处理，不进入 Core 请求体。

### 请求与输出

- 方法：`POST`
- 路径：`/api/v1/novels/{url-encoded-novelId}/chapters`
- 请求体：无
- 输出：原样保留 Core 返回的 JSON，其中包含新建章节。
- 命令属性：mutation、需要身份、不需要 `clientRequestId`、无文件输出。

章节创建由 Core 在事务和小说行锁内分配下一顺序。CLI 不自行计算 order，也不做本地镜像。

## 生产长篇工作流

### 1. 接管与恢复优先

每轮先执行身份校验，定位小说，完整查询章节、会话、任务和待审 Artifact。若已有非终态任务或待审
Artifact，先恢复并处理；不得同时为同一章节启动重复任务。

### 2. 创作准备门禁

开始某章前，至少确认：

- 目标章节存在；不存在时使用 `long.chapter.create` 创建，并立即重新查询章节取得权威 ID 与版本。
- 前序正式章节已回拉，且当前章承接关系可判断。
- 当前章具备可执行的章节目标。作品总大纲为空不必机械阻止单章创作，但若当前章目标、冲突、推进和
  章尾钩子均无法从已批准设定、前文或用户锁定意图中确定，则停止并向用户说明缺失规划。
- 当前设定、资源和相关规划已经回拉；不能用本地记忆代替 Core 当前状态。

### 3. 单章闭环

每章严格按以下顺序执行：

1. `plan_chapter`：启动规划任务并观察至待审 Artifact。
2. 完整读取 Beat Plan、Diff、来源绑定和 revision，取得该 Artifact 的独立用户决策。
3. 批准后继续观察原任务至终态，并回拉已应用的章节规划。
4. `write_chapter`：以上一阶段正式结果为输入生成正文候选。
5. 完整读取正文候选、Diff、来源绑定和 revision，取得该 Artifact 的独立用户决策。
6. 批准后继续观察原任务至终态，回拉正式章节并核对标题、正文、字数和更新时间。
7. 按用户要求或明显质量风险运行 `review_chapter` / 质量检查；质量报告不自动改写正文。

### 4. 连续多章

连续创作必须逐章串行：第 N 章正式写入并回拉验证后，才能规划第 N+1 章。后章必须读取前章正式正文，
不能基于尚未批准的候选继续生成。创建缺失章节也按需要逐个创建并立即回拉，不预先猜测章节 ID。

用户说“连续写完”只授权启动相应章节的创作流程，不等于自动批准任何 Artifact。每个 Beat Plan、正文
候选和返工候选仍需独立决定；等待决定时流程暂停在该章，不越过到下一章。

### 5. 返工路由

- 仅有少量、明确、可机械描述的正文修改时，优先在 `long.artifact.approve` 的 `editedContent` 中提交
  完整修改后正文，保留候选到正式写入的一次决策闭环。
- Beat Plan 不得通过 `editedContent` 修改；Core 会忽略该字段并应用原始规划。规划需要修改时必须使用
  `long.artifact.revise` 生成新 revision 后重新决策。
- 需要重新组织场景、人物行动、节奏或大段文风时，使用 `long.artifact.revise` 让 Agent 返工，再读取
  新 revision 重新决策。
- `editedContent` 只有 `approve` 分支会应用。`revise` 请求即使携带该字段也会被 Core 忽略；操作员不得
  携带该字段或假装 `revise` 能做局部直改。
- Artifact 已应用后的人工章节修改属于新的正式写入，必须使用章节当前 `updatedAt`、完整 Diff、一次
  明确授权和写后回拉验证。

### 6. 停止条件

出现以下任一情况立即停止新增写入并对账：身份不符、生产接口未部署、来源未验证、CAS/revision 冲突、
网络结果不确定、任务或 Artifact 状态无法解释、当前章缺少可执行目标、前章正式结果未确认、CLI 能力门禁
数量不匹配。禁止使用 SSH、数据库、内部接口或自制 HTTP 绕过。

## 能力计数

增加该命令后，生产授权集合调整为：

- 79 条总命令；
- 63 条 long 命令；
- 46 条 long mutation；
- 33 条长篇结构化创作资料写命令保持不变。

## 验收

1. CLI 单元测试证明命令发送准确的 POST 路径、无请求体、编码 novelId，并拒绝缺失/空 novelId。
2. registry 测试证明命令存在、属性正确，精确计数更新。
3. 生产 Skill 测试证明 wrapper 只新增这一条命令且没有通配符。
4. Skill 文本测试证明包含准备门禁、逐章串行、独立 Artifact 决策、小改/大改返工路由和停止条件。
5. 相关 pytest、PowerShell Skill 测试、Ruff 与 Mypy 全部通过。
6. 用未接触实现意图的独立代理重新执行基线场景，确认它能依据 Skill 给出稳定且安全的连续创作方案。
