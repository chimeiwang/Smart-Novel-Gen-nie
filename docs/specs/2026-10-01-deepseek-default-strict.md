# DeepSeek 工具调用默认启用 strict

状态：实现、生产发布及 30 分钟稳定观察完成，未进行真实供应商验收；见 [验收记录](../audits/2026-10-01-deepseek-default-strict.md)。范围是供应商 Function Calling 的 Beta `strict`，不是 Pydantic 严格校验。

## 目标与边界

- DeepSeek 工具声明未指定 strict 时，默认使用 `/beta/chat/completions`，同一请求全部函数发送 `strict: true`。
- 同时覆盖 `deepseek_v4` 原始传输与 `generic` 下的 DeepSeek 工具调用；其他供应商沿用原默认。
- 显式关闭 strict 仍可用于兼容请求；同一请求中启用与关闭混用必须在 HTTP 前失败，不自动降级。
- 保留质量报告已经使用的专用 wire 契约；普通工具需要适配 DeepSeek Schema 子集，并在返回业务层前完整复验原 Schema。
- 纯文本没有 Function Calling strict 开关；现有 `chat_json_output_v1`、视频 Responses 与耐久任务冻结路由本次不转换协议。
- 不修改数据库、公共接口、计费、纠正预算、内容采用流程；首轮实现未部署、未调用真实供应商。
- 2026-10-01 用户追加授权“提交并部署”：提交本次改动并按现有生产流水线发布，保留全部健康、结构、镜像与回滚门禁，不扩大为数据库变更、视频开放或业务内容写入。

## 设计

1. 工具 strict 使用三态：未指定由 Provider 决定；true/false 保留明确意图。注册表的普通工具不再隐式指定 false。
2. DeepSeek 在统一供应商边界选择默认值、编译 wire Schema、编码进程内工具历史、解码响应。
3. 每个 wire 对象闭合、至少包含一个属性且所有属性必填。普通可省略字段使用显式存在性包装，nullable 使用显式空值包装，避免把空字符串、零、false、空数组或空对象误当缺失/null。无参工具、业务空对象、省略和 null 的表示使用固定标记字段，解码后恢复各自原值；修复依据见[空对象兼容规格](2026-10-07-deepseek-strict-empty-object.md)。
4. 本地引用解析；开放字典及任意/递归 JSON 使用说明明确的 JSON 字符串传输并严格解析，不能因闭合对象而丢弃业务字段。定位与复审的 anyOf 组合展开为完整对象分支，继续在 wire 中约束；供应商不支持的长度等限制保留说明并由原 Schema/Pydantic 校验。
5. 无效 wire、解码失败或原 Schema 不通过时保留可靠 usage，返回现有脱敏无效工具诊断，禁止工具副作用；不新增模型重试。
6. 官方 HTTPS 根地址和 `/v1` 自动派生 `/beta`；自定义网关沿用显式 `OPENAI_STRICT_BASE_URL`，缺失则在 HTTP 前失败。

## 验收

- 普通读取、正文提交、Reviewer、Beat Plan、设定更新与质量终检的实际请求都按默认值走 strict；覆盖多工具请求与思考模式。
- 两种 DeepSeek Provider 的默认开启、显式关闭、混用拒绝、端点与零回退均有传输替身验证。
- 可省略/null/空值、动态 JSON、嵌套数组与历史回放无损；完整业务 Schema 保留，错误响应不进入工具执行。
- 非 DeepSeek、纯文本、既有结构化路由和质量专用映射回归通过。
- 运行相关及 Agent Python 测试、`uv run ruff check .`、共享范围 Mypy 与 `git diff --check`。

## 依据

- [DeepSeek 官方 Tool Calls](https://api-docs.deepseek.com/zh-cn/guides/tool_calls/)：Beta 地址、所有函数 strict、闭合且全必填对象及支持的 Schema 子集。
- 取代 Agent 指导与需求中“只有质量终检使用 strict、其他 strict 工具拒绝”的旧限制；不改变历史任务冻结的结构化输出路由。
