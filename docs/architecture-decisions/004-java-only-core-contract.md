# ADR-004：Java Core 唯一接口契约与旧 Python 实现退役

日期：2026-09-12

状态：已接受；实现与验收以清理规格和审计为准

## 决策

`contracts/core/openapi.json` 是唯一可编辑的 Core HTTP 契约。它使用 OpenAPI 3.0.3，保留既有 required、null、
枚举、operationId、错误与流响应语义。Java Core、Java DTO、Java CLI 与 TypeScript 客户端从该契约及其公共
投影生成；投影器与漂移检查不启动 Python 或 Core。`x-inkforge-exposure` 决定 public／internal／provider media，
不能只凭 `/api/v1` 前缀分类。

Java 生成接口与实际 Controller 映射双向核对所有操作，健康接口也参与覆盖。语言中立错误、HTTP、SSE、服务身份
和行为 golden fixtures 继续作为独立预期，不通过重新生成自身预期规避兼容检查。

删除 Python Core、Python CLI、迁移期双 Core 差异运行器和 Python Core 回滚入口。结构契约由 Java 自有资源和
只读导出／守卫维护。`apps/core-api-java` 是正式 Core 目录，无须再为后缀做大规模重命名。

Python Agent、它使用的 Pydantic 契约和 Ed25519 鉴权库保留。Agent 的独立性指只依赖版本化服务协议，不依赖
Java 实现或数据库；仍必须遵守 Core 内部工具网关、运行和回调契约。

Windows Operator 保持已安装的 84 命令／五操作投影；既有 macOS 45 命令／三操作投影独立保留，均不因
普通 CLI 当前 152 命令而自动扩大授权。

## 取代范围

本决策取代 ADR-002 的 Python Core 契约来源与迁移期双实现要求，以及 ADR-003 的 Python Core 回滚目标。
单 Core、单数据库业务所有者、真实 PostgreSQL 验证、V2 兼容回滚和禁止自动 DDL 的约束继续生效。

## 选择理由

现有 Java API interface 与 DTO 已由 OpenAPI 生成。保留明确契约源可避免 Spring 运行时反向导出造成循环依赖，
也能使生成器升级、流响应和可空语义变化有可审查 diff。历史兼容证据由 Git 和 golden fixtures 保留。

清理不构成生产部署、数据库迁移或视频开放授权。完整范围见
[Java-only 清理规格](../specs/2026-09-12-java-only-core-contract-and-python-retirement.md)。
