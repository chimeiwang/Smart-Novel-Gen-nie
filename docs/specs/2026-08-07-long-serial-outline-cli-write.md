# 长篇大纲正文 CLI 安全写入规格

## 状态

- 日期：2026-08-07
- 状态：实现完成，待部署与生产验证
- 适用范围：`long_serial` 长篇小说、`inkforge-cli`、生产与本地操作 Skill
- 用户确认：只开放整份大纲正文保存，不开放结构化大纲节点写入

## 目标

新增 `long.outline.save`，让 CLI 通过现有公共 Core API 保存长篇小说的整份大纲正文。写入必须具备并发保护、完整文本传输和写后校验能力，不新增 Core 接口，不修改 PostgreSQL schema。

## 命令契约

```text
long.outline.save
```

命令注册元数据固定为：

- `inputMode=json`
- `outputMode=json`
- `mutation=true`
- `requiresIdentity=true`
- `requiresClientRequestId=false`
- `fileOutput.kind=none`

输入字段：

```json
{
  "novelId": "小说 ID",
  "content": "完整大纲正文",
  "expectedUpdatedAt": "读取大纲时得到的非空 UTC 时间戳"
}
```

`content` 与 `contentFile` 必须且只能提供一个。`contentFile` 按 UTF-8 原样读取，不规范化换行、不截断文本。`expectedUpdatedAt` 必须是非空字符串，不接受 `null`，因为长篇小说创建时已经存在大纲记录。

CLI 发送：

```text
PUT /api/v1/novels/{novelId}/outline
```

请求体只包含 `content` 和 `expectedUpdatedAt`。响应完整透传 Core 返回的 `id`、`content`、`contentHash`、`createdAt` 和 `updatedAt` 等字段。

## 安全与恢复

1. 操作方先执行 `long.planning.get`，保存当前完整正文和 `updatedAt`。
2. 写入前展示完整旧正文、新正文和 Diff，获得一次明确确认。
3. 使用读取到的 `updatedAt` 执行一次 `long.outline.save`。
4. `OUTLINE_VERSION_CONFLICT` 时停止，重新读取并重新确认，不自动替换版本重试。
5. 网络结果不确定时先执行 `long.planning.get`：若正文与目标完全一致则视为成功；否则使用原 `expectedUpdatedAt` 原样重放，并接受 Core 的 CAS 结果。
6. 成功响应后再次执行 `long.planning.get`，核对完整正文、`updatedAt` 和可用的内容哈希。

## 非目标

- 不开放 `long.outline-node.create/update/delete`。
- 不改变 `plan_chapter`、Agent、ReviewArtifact 或章节写作链路。
- 不增加本地大纲镜像、manifest、dirty gate 或批量导入。
- 不修改 Core API、OpenAPI、数据库结构或生成客户端。

结构化大纲节点现有公共写接口尚无稳定 `clientRequestId` 和逐实体 CAS，继续保留为未注册命令。

## 测试与验收

- 注册表只新增 `long.outline.save`，命令总数和长篇写命令数各增加 1。
- 精确校验路由、请求体、URL 编码和注册元数据。
- 校验 `content`/`contentFile` 二选一、UTF-8 原文、未知字段拒绝。
- 校验 `expectedUpdatedAt` 缺失、`null`、空串和非字符串均在本地拒绝，不发起请求。
- README 命令清单与注册表保持完全一致。
- 生产 Operator Skill 的精确 allowlist、命令计数与烟雾测试同步更新；本地 Operator Skill 的命令说明和流程测试同步更新。
- 生产验证按 `whoami -> planning.get -> outline.save -> planning.get` 执行，且不得用测试文本覆盖正式大纲。
