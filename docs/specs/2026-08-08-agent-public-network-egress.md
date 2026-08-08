# Agent 生产模型公网出口

## 背景

生产 `agent-service` 仅连接 `agent_net`，而该网络配置为 `internal: true`。运行态容器没有默认外网路由，调用模型供应商时在域名解析阶段失败，公开任务错误为 `MODEL_PROVIDER_FAILED`。

## 决策

- `agent-service` 同时连接 `agent_net` 与现有 `public_net`。
- `agent_net` 继续承载 Core、Agent 与 Redis 的内部通信。
- `public_net` 为 Agent 提供访问模型供应商所需的公网出口。
- Core 与 Agent 的内部服务地址使用 `agent_net` 专用网络别名，避免共享 `public_net` 后服务名解析到 `172.28.0.0/24`。
- Agent 继续禁止连接 `data_net`，不得获得 PostgreSQL 访问能力。
- Agent 不发布宿主机端口，Nginx 继续阻止公网 `/internal/` 路由。

## 验证

- 架构测试要求 Agent 同时连接 `agent_net` 与 `public_net`，且不连接 `data_net`。
- 架构测试要求 `AGENT_SERVICE_URL` 与 `CORE_API_URL` 使用各自在 `agent_net` 上声明的专用别名。
- `docker compose config` 必须成功渲染生产编排。
- 本地验证与生产相同网络条件下能够解析并请求模型供应商。
- 部署后从 Agent 容器执行最小模型调用，再启动一次新的章节写作任务。
