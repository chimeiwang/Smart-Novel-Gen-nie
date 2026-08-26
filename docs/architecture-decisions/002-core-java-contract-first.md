# ADR-002：契约优先与差异测试

日期：2026-08-24

状态：已接受

## 背景

当前 Web、Python Agent、Python CLI、数据库和运维脚本都依赖 FastAPI Core 的具体行为。只按业务名称
重写会遗漏 operationId、nullability、错误码、Cookie、SSE 游标、内部签名、事务副作用和失败恢复。

## 决策

1. Python Core 在迁移期间是行为基线；
2. 导出并版本化公共 OpenAPI、内部路由、错误、SSE 和服务鉴权 fixtures；
3. 每个 Java 行为先有失败测试，再实现；
4. Python 与 Java 差异测试使用两个隔离 PostgreSQL，比较归一化 HTTP 结果和数据库快照；
5. Java OpenAPI 必须匹配冻结基线，TypeScript 客户端最终由 Java OpenAPI 生成；
6. Core/Agent 契约新增语言中立 JSON Schema，Python Pydantic 与 Java records 共同验证；
7. 未经新 spec 批准不得改变公共或内部契约。

## 归一化边界

差异测试只归一化动态 ID、时间、随机 token、无语义顺序和服务地址。以下内容不得归一化掉：

- HTTP 方法、路径、状态码和 Content-Type；
- operationId、字段 required/null、枚举和未知字段拒绝；
- 中文错误 code/message/details 和 requestId；
- Cookie 名称、claims、有效期和安全属性；
- SSE event、id、序号、终态和重连行为；
- 数据库写入数量、状态、版本、哈希、账本和 Outbox；
- 文件字节、SHA-256、媒体类型和清理结果；
- Ed25519 audience、权限、摘要、时钟和重放语义。

## 后果

- 迁移前期会先增加大量 fixtures 和测试，而不是快速堆接口；
- Python Core 测试在观察期结束前不能删除；
- 任何契约差异都必须明确判断为缺陷或获批变更；
- 覆盖率只提示遗漏，不能替代行为断言和差异测试。
