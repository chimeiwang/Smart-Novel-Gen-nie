# 生产部署就绪稳定化规格

## 状态

- 日期：2026-07-15
- 状态：已批准
- 范围：生产 Smoke、Agent readiness 稳定窗口、Nginx upstream 刷新

## 背景

生产部署在 `docker compose up --wait` 返回成功后，Agent 队列消费者可能进入监督器退避。Docker 健康状态按固定间隔采样，短时间内仍会显示 `healthy`，而紧随其后的单次 Agent readiness 请求会收到 503 并立即触发回滚。

现有 Smoke 还默认访问宿主机 80 端口，没有从 Compose 获取 Nginx 的实际发布端口；应用容器重建后，长期运行的 Nginx 也可能继续使用启动时解析的旧 upstream 地址。

## 目标

- 不忽略 Agent readiness 失败，不降低现有回滚保护。
- 容忍监督器一次性短暂退避，只在 Agent 连续稳定就绪后放行。
- 持续失败或反复抖动必须在有界时间内失败并触发原有回滚。
- 503 时仅输出白名单 readiness 诊断，保留 `backgroundTasks` 错误码且不泄露其他响应字段。
- Smoke 必须验证当前 Compose Nginx 的真实发布端口。
- Web、Core 或 Agent 容器切换后刷新 Nginx 的 Docker DNS 解析。

## 设计

### Agent 稳定探针

`scripts/compose_smoke.sh` 对 Agent 内部 readiness 进行有界轮询；每次通过标准输入在 Agent 容器内执行独立的 `scripts/agent_readiness_probe.py`，并把固定内部 URL 作为唯一参数传入：

- 默认最多检查 45 次，每次间隔 2 秒；
- 默认要求连续 5 次返回 200 且 JSON `status` 为 `ready`；
- 任意失败都会把连续成功次数清零；
- 探针用 `with` 关闭 HTTP 错误响应，只输出顶层 `status`、`checks`、`backgroundTasks`；非法 JSON 只输出 HTTP 状态码；
- Smoke 只转发探针带安全前缀的诊断，丢弃 Docker 或其他进程的非结构化失败输出；
- 达到最大次数仍未稳定时返回非零。

检查次数、连续成功次数和间隔允许通过仅用于测试/演练的环境变量缩短，但生产默认值保持上述约束。

### Nginx 发布端口

Smoke 使用 `docker compose port nginx 8080` 获取当前发布端口，并只接受可解析的数字端口。不得 `source .env`，避免执行配置文件内容，也避免与 Compose 的环境变量解析规则产生差异。

### Nginx upstream 刷新

新版本全栈 `compose up --wait` 完成后，部署脚本使用当前镜像和配置强制重建 Nginx 容器，再执行 Smoke。自动回滚恢复旧应用容器后执行同样的 Nginx 刷新，确保两条路径都不会保留旧 upstream 地址。

## 错误处理

- 无法解析 Nginx 发布端口时直接失败。
- Agent 503 或 200 未就绪响应只允许输出顶层 `status`、`checks`、`backgroundTasks`，不得原样输出响应体或输出其他字段。
- Agent 返回非法 JSON 时只允许输出 HTTP 状态码。
- Agent 在观察窗口内恢复且满足连续成功次数时继续部署。
- Agent 持续未就绪、周期性抖动或 Nginx 刷新失败时保留原有自动回滚语义。

## 测试与验收

- 行为测试模拟 Agent `503 -> ready -> 连续 ready`，证明达到稳定窗口后成功。
- 行为测试模拟持续 503，证明达到上限后失败且日志包含 readiness JSON。
- 独立探针测试使用本机 `127.0.0.1` 随机端口 HTTPServer，真实覆盖 200 ready、503 安全诊断、200 未就绪和 503 非法 JSON，不访问外网。
- 测试断言 Smoke 请求 Compose 返回的实际 Nginx 端口，不再默认命中 80。
- 部署脚本测试断言新版本和回滚路径都会强制刷新 Nginx。
- 运行部署脚本架构测试、回滚测试、Compose 安全测试和 Shell 语法检查。
