# 长篇 CLI 总体交付 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不新增本地业务状态、不修改 PostgreSQL schema 的前提下，交付可恢复、可取消、具备来源版本保护的长篇章节生产 CLI，并完成生产环境验证。

**Architecture:** Core API 是唯一业务权威；Agent Service 只执行显式 Operation 并通过签名内部工具网关回写；CLI 只做无状态命令映射、完整文件 I/O 与任务观察。实施分为控制面、运行安全、CLI 章节闭环、生产发布四份计划，任何长篇写命令都必须等服务端安全门槛通过后才能注册。

**Tech Stack:** Python 3.12、FastAPI、Pydantic v2、SQLAlchemy async、PostgreSQL advisory/row locks、Redis/Lua、LangGraph、httpx、Next.js 16 生成客户端、pytest、Ruff、Mypy、PowerShell

---

## 交付范围

本计划一次覆盖首个可上线的长篇章节闭环：

```text
显式 plan_chapter
-> ReviewArtifact revise/approve
-> 显式 write_chapter
-> 来源冲突保护
-> ReviewArtifact approve
-> 章节 review
-> 显式 review_chapter 与完整审核报告
-> 质量检查
-> 章节 completed
```

同时交付任务 list/get/watch/resume/cancel、Artifact list/get/decision、章节人工 CAS 写入、进展 CAS、质量幂等/CAS，以及独立生产长篇 Skill。

以下边界固定不变：

- 不增加全局“篇幅模式守卫”；用户已明确不需要。
- 不修改 PostgreSQL schema、迁移或 `schema-contract.json`。
- 不创建本地 manifest、任务账本、业务镜像、dirty gate 或 production snapshot。
- 不通过 CLI 创建小说或章节；首版从 Web 已创建的长篇与章节接管。
- 不改变中短篇版本、manifest、confirmationHash、watcher 退出码和业务语义。
- 不把 SSE、Agent 文本或本地文件当成最终状态；最终状态只由 Core 的 PostgreSQL outcome 决定。

## 实施基线

在隔离且已核对状态的实现工作树中、修改任何实现文件前，固定一次本地 Git 基线：

```powershell
git status --short --branch
git update-ref refs/codex/long-serial-plan-base HEAD
git rev-parse refs/codex/long-serial-plan-base
```

四份子计划都用 `refs/codex/long-serial-plan-base` 检查从实施开始到当前 HEAD 的完整差异。该 ref 只保存在本地，不推送；在生产闭环和最终审计全部完成前不要删除或改写它。

## 计划依赖

```text
01 控制面与共享契约
   ├──> 02 运行安全与正式写入门禁
   └──> 03 CLI 的注册表、普通只读命令和 watcher

02 的 Artifact 列表/sourceBindingStatus 切片通过
   └──> 03 注册 long.artifact.list/get 的完整只读行为

02 全部通过
   └──> 03 注册章节闭环写命令

01 + 02 + 03 全部通过
   └──> 04 Task 1：同步仓库权威文档

01 + 02 + 03 + 生产 HTTPS 计划 Task 7 全部通过
   └──> 04 Task 2–10：迁移/创建生产 Skill、离线验证、发布与真实闭环冒烟
```

执行文件：

1. [控制面与共享契约](./2026-08-05-long-serial-control-plane.md)
2. [运行安全与正式写入门禁](./2026-08-05-long-serial-runtime-safety.md)
3. [CLI 章节闭环](./2026-08-05-long-serial-cli-chapter-loop.md)
4. [生产发布与操作 Skill](./2026-08-05-long-serial-production-rollout.md)

## 实施批次与开放门槛

### 批次 1：控制面

- [ ] 完成共享长篇 payload、公开 Operation 投影和 Agent 一致性校验。
- [ ] 完成 Core 规范化、请求指纹、章节目标互斥和来源冻结。
- [ ] 完成任务列表、状态扩展、稳定 cursor 和 outcome 归一。
- [ ] 完成显式 Operation 直通，证明不会进入自然语言 classifier。
- [ ] 只允许合并服务端契约；此时不注册任何长篇 CLI 写命令。

### 批次 2：安全门禁

- [ ] 完成 cancel 持久命令、Redis tombstone 和运行中取消检查。
- [ ] 完成写型内部请求 `jobId` 绑定和迟到 job 硬拒绝。
- [ ] 完成 Artifact 控制字段、来源校验、expectedRevision 和列表。
- [ ] 完成 progress CAS、quality run 幂等、quality skip/reset CAS。
- [ ] 完成并发竞态、死锁、迟到 callback 和 schema 指纹测试。

只有本批次全部通过，才允许注册以下写命令：

```text
long.chapter.save
long.chapter.status
long.chapter.progress.save
long.agent.start
long.task.resume
long.task.cancel
long.artifact.approve
long.artifact.revise
long.artifact.discard
long.quality.run
long.quality.skip
long.quality.reset
```

### 批次 3：CLI

- [ ] 先以 characterization tests 完成注册表和模块化重构。
- [ ] 注册全部长篇查询命令和只读 `long.task.watch`。
- [ ] 在批次 2 门槛通过后，按章节、任务、Artifact、质量四个垂直切片注册写命令。
- [ ] 验证完整 UTF-8、80,000 字以上文本、JSONL、退出码与中短篇兼容。

### 批次 4：生产发布

- [ ] 先完成 `docs/plans/2026-08-05-production-https.md` Task 7，确认 `https://inkforge.cn`、Secure Cookie、Compose loopback 和中短篇生产 Skill schema v3 已生效；不得回退公网 IP HTTP。
- [ ] 将现有中短篇 wrapper 的硬编码授权迁移为显式 policy，授权集合保持完全相同。
- [ ] 创建独立生产长篇 Skill；policy 只列出已发布的具体命令，不使用通配符。
- [ ] 提交、披露完整 ahead 范围、推送、监控部署终态。
- [ ] 只读冒烟后，在专用长篇测试作品上跑完整单章闭环和取消场景。

## 固定的实现细节

规格中的两处未完全展开字段在实施前按以下形状补充到规格，不留给各服务自行解释：

```json
{
  "resourceType": "approved_beat_plan",
  "resourceId": "chapter:<chapterId>:approved_beat_plan",
  "exists": false,
  "updatedAt": null,
  "contentSha256": null,
  "revision": null,
  "absenceSentinel": {
    "resourceType": "chapter",
    "resourceId": "<chapterId>"
  }
}
```

- 不存在 Outline 的逻辑 `resourceId` 固定为 `novel:<novelId>:outline`，sentinel 指向 Novel。
- 不存在 approved Beat Plan 的逻辑 `resourceId` 固定为 `chapter:<chapterId>:approved_beat_plan`，sentinel 指向 Chapter。
- `exists=false` 时版本、hash、revision 全为 `null` 且 sentinel 必填；`exists=true` 时 sentinel 为 `null`。
- 公开 checkpoint 只投影 `eventSequence/phase/operationStage/operationStep`，不泄露完整 LangGraph 快照。

新增幂等写的现有列存储格式固定为：

```json
{
  "_inkforgeCommand": {
    "schemaVersion": 1,
    "clientRequestId": "caller-owned-id",
    "commandKind": "start",
    "resourceIdentity": {"novelId": "...", "chapterId": "..."},
    "normalizedBody": {},
    "requestFingerprint": "64位小写SHA-256"
  },
  "job": {}
}
```

- `WritingRunCommand.payloadJson` 使用 `_inkforgeCommand + job`；Agent 只收到严格校验后的 `job`。
- 历史 command 没有该 envelope 时继续按旧 payload 读取，但不能命中新幂等请求。
- `WorkflowRun.input` 使用同一个 `_inkforgeCommand`，业务输入放在 `quality` 字段。
- Artifact/Revision 的来源指针仍使用规格固定的 `_inkforgeControl.sourceCommandId`，与命令 envelope 分离。

## 暂不注册的结构写命令

以下名称属于后续产品面，不属于这四份可执行计划的实现范围：

```text
long.outline.save
long.outline-node.create/update/delete
long.foreshadowing.create/update/delete
long.lore.<resource>.create/update/delete
long.reference.create/update/delete/reindex
long.style.apply/clear
```

原因不是 CLI 缺 handler，而是相应公共资源尚未逐类具备可持久幂等、CAS、原子事务、删除影响和完整 sourceBindings。后续必须分别新增 planning、outline node、foreshadowing、lore、reference、style 垂直规格；在那些规格通过前，registry 与生产 policy 都不得出现这些名称。

## 全局完成定义

- [ ] 四份计划中的测试与静态检查全部通过。
- [ ] `npm run api:generate` 后 `npm run api:check` 无差异。
- [ ] `npm run typecheck`、`npm run lint`、`npm run test:web` 通过。
- [ ] `uv run pytest` 的相关 Core、Agent、contracts、auth、CLI 测试通过。
- [ ] `uv run ruff check .` 与指定 Mypy 范围通过。
- [ ] 数据库 schema 指纹只读校验通过，确认没有 DDL/模型元数据变化。
- [ ] 中短篇 CLI 全量回归通过。
- [ ] 生产部署终态已监控，不把“push 成功”当成“部署已验证”。
- [ ] 生产单章闭环和 cancel 冒烟通过，正文尾部与错误详情完整。

## 提交策略

每份子计划按其任务给出的 commit 边界提交。仓库内实现与文档可以提交并推送；以下个人 Skill 路径不属于 `F:\code\inkForge` Git 仓库，必须单独披露验证结果，不能声称随仓库 push 发布：

```text
C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\**
C:\Users\niebo\.codex\skills\inkforge-production-long-novel-operator\**
```
