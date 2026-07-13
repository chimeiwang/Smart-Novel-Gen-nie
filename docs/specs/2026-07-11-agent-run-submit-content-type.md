# 智能体运行提交媒体类型修正规格

## 目标

修复 Core API 向 Agent Service 提交运行任务时稳定返回 `422 Unprocessable Entity`，并在请求体解析后因密钥标识不一致返回 `401 Unauthorized` 的问题。

## 非目标

- 不修改 PostgreSQL schema 或已有数据。
- 不调整服务签名协议、任务协议字段、Redis 队列或智能体执行流程。
- 不扩展部署、压测和灾难恢复验证。

## 设计

Core API 与 Agent Service 继续对 `canonical_json_body()` 生成的原始字节进行签名和发送，同时显式声明 `Content-Type: application/json`。服务密钥生成脚本产出的 JWKS `kid` 必须与 Core API、Agent Service 和 Compose 的默认密钥标识一致。签名请求体、幂等键和资源绑定保持不变。

## 影响范围

- Core API 的 Agent 运行提交客户端。
- Core API 对应的客户端单元测试。
- Agent Service 的 Core 回调客户端及其集成测试。
- 服务密钥生成脚本及其测试。

## 验收标准

- 双向服务客户端提交 JSON 请求时均包含 `Content-Type: application/json`。
- 新生成的双向 JWKS 使用服务默认配置中的密钥标识。
- Agent Service 能把同一份规范化请求体解析为 `AgentJobRequest` 并返回 `202`。
- 现有服务签名与运行提交测试通过。
