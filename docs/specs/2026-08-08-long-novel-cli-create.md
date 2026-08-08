# 长篇小说创建 CLI 规格

## 背景

Core 已通过 `POST /api/v1/novels` 支持 `storyLengthProfile=long_serial`，并在创建成功后返回
`novelId` 与首章 `chapterId`。当前公开 CLI 只有 `long.novel.list` 和 `long.novel.get`，导致本地与
生产 Operator 无法在不使用 Web UI 的情况下新建长篇项目。

## 目标

新增公开命令 `long.novel.create`，只创建长篇项目，并同步本地、生产两个 Operator Skill。底层复用
现有 Core 公共接口，不修改 Core 契约、PostgreSQL schema、Agent Service 或前端。

## 命令契约

输入为 UTF-8 JSON 对象：

- 必填：`name`，必须是去除首尾空白后仍非空的字符串；
- 可选：`summary`、`targetTotalWordCount`、`genre`、`protagonist`、`coreSellingPoint`、
  `readerPromise`、`firstChapterGoal`；
- 本地运行字段：`profile`；
- 禁止调用方传入 `storyLengthProfile`、`clientRequestId`、`sourceKind`、`sourceText`、
  `outputFile` 或其他未知字段。

CLI 固定向 Core 发送 `storyLengthProfile: "long_serial"`。命令声明为需登录的写命令，不要求
`clientRequestId`，因为当前 Core 的长篇创建契约明确拒绝该字段。

## 结果与故障恢复

成功时完整返回 Core 的 `novelId` 与 `chapterId`。调用方随后必须使用 `long.novel.get` 和
`long.chapter.get` 验证新项目及首章。

由于长篇创建当前没有幂等键，连接中断或响应不确定时不得直接重试。先执行 `long.novel.list`，按名称、
篇幅、摘要和目标字数定位候选，再对候选执行 `long.novel.get`、`long.planning.get` 和首章回拉，核对公开
可观察字段。仍无法唯一确认是否已创建时必须停止，不能再次提交。

## 验收

- CLI 注册表包含 `long.novel.create`，元数据为写命令、需身份、不要求请求 ID、无文件输出；
- 合法字段原样转发，并固定加入 `storyLengthProfile=long_serial`；
- 缺少名称、名称为空、类型错误、短篇专属字段和未知字段均在发起 HTTP 前失败；
- CLI 测试、Ruff、Mypy 通过；
- 本地与生产 Operator 的命令清单、流程说明、恢复说明和测试保持业务语义一致。
