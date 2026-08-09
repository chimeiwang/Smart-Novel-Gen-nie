# 长篇作品摘要安全写入规格

## 背景

当前 `long.novel.create` 允许在创建长篇时填写摘要，但公开 Core 与 CLI 均没有修改已有作品摘要的能力。
`Novel.summary` 已存在于当前 PostgreSQL schema，因此本需求不修改数据库结构。

## 目标与边界

- Core 新增窄接口 `PUT /api/v1/novels/{novelId}/summary`；
- CLI 新增 `long.novel.summary.save`；
- 只允许修改 `Novel.summary`，不顺带开放名称或其他作品字段；
- 不修改 Agent Service、ReviewArtifact 状态机或前端页面；
- 新公共接口必须重新生成 TypeScript API 客户端。

## Core 契约

请求体：

```json
{
  "summary": "新的作品摘要",
  "expectedUpdatedAt": "2026-08-09T00:00:00Z"
}
```

- `summary` 必须为字符串或 `null`；去除首尾空白后为空时按 `null` 保存，用于清空摘要；
- `expectedUpdatedAt` 必须是严格的 JSON datetime，来自本轮 `GET /api/v1/novels/{novelId}`；
- 返回更新后的完整 `NovelResponse`；
- 用户只能更新自己的作品；不存在返回 `NOVEL_NOT_FOUND`，归属不符返回 `NOVEL_FORBIDDEN`；
- 版本不一致返回 409 `NOVEL_VERSION_CONFLICT`，details 包含当前 `currentUpdatedAt`；
- 新值与当前值相同时为幂等成功，不推进 `updatedAt`；真实变化时使用单调递增时间推进版本。

## CLI 契约

命令输入：

```json
{
  "novelId": "novel-id",
  "summary": "新的作品摘要",
  "expectedUpdatedAt": "2026-08-09T00:00:00Z"
}
```

- 必填字段恰为 `novelId`、`summary`、`expectedUpdatedAt`，另允许本地 `profile`；
- `summary` 只接受字符串或 `null`，`null` 表示清空；
- 拒绝 `outputFile`、`clientRequestId` 和所有未知字段；
- 命令是需身份的普通 JSON 写命令，不要求 `clientRequestId`，不声明文件输出；
- 精确映射到 `PUT /api/v1/novels/{novelId}/summary`。

## Operator 流程

本地与生产 Skill 业务语义相同：

1. `long.novel.get` 读取当前摘要与 `updatedAt`；
2. 展示完整旧值、新值和 Diff，取得针对该 Diff 的一次明确确认；
3. 使用该版本执行一次 `long.novel.summary.save`；
4. 再次 `long.novel.get`，核对摘要和新版本；
5. 409 时重新 GET、重新展示 Diff、重新确认，禁止自动替换版本重试。

摘要属于作品元数据写入，不计入 33 条长篇创作资料结构化写命令。能力计数更新为：
`81 total / 65 long / 48 long mutation / 33 structured writes`。

## 验收

- Core schema、service、repository、router 的严格契约、归属和 CAS 测试通过；
- CLI 映射、字段白名单、null 清空和 CommandSpec 测试通过；
- OpenAPI 客户端重新生成且检查通过；
- CLI/相关 Core 测试、Ruff、Mypy、TypeScript 检查通过；
- 两个 Skill 先有失败契约测试，再同步命令、流程、计数和恢复规则，并通过全部验证。
