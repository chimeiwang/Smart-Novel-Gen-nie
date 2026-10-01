# DeepSeek 默认 strict 仓内验收

日期：2026-10-01。环境：本地 macOS 工作区，使用仓库现有 `.venv`。

## 结果

已完成 [默认 strict 规格](../specs/2026-10-01-deepseek-default-strict.md) 的仓内实现与测试。
未部署、未调用真实 DeepSeek，不能以本记录证明供应商实测或生产已生效。

- `deepseek_v4` 与 `generic` 下的 DeepSeek 工具请求均默认使用 Beta 端点及全部函数 `strict: true`。
- 45 个注册工具的 wire Schema 通过子集检查；HTTP 替身覆盖读取、正文、复审、节拍、质量报告，以及多工具、显式关闭和混用拒绝。
- 省略、null、空串、动态 JSON 与工具历史保持可逆；正文完整保留；条件字段组合、派生计数、原业务 Schema 校验继续生效。
- 非 DeepSeek、纯文本、既有 JSON Output、视频与 V2 质量执行回归通过。
- 保留任务开始前已有的 `docs/README.md` 代理入口、未跟踪代理规格、`.vscode/` 与代理配置文件。

## 验证命令

当前 shell 未提供 `uv`，因此使用现有虚拟环境内的等价工具入口，没有安装或改动依赖。

| 命令 | 结果 |
| --- | --- |
| `.venv/bin/pytest apps/agent-service/tests -q --tb=short` | 1890 通过；1 条既有 Starlette/httpx 弃用提示 |
| `.venv/bin/ruff check .` | 通过 |
| `.venv/bin/mypy apps/agent-service/src packages/service-contracts/src packages/service-auth/src` | 132 个源文件通过 |
| `git diff --check` | 通过 |
| 本次新增文档相对链接检查 | 通过 |

质量执行 HTTP 替身已修正为按既有 wire 返回空字符串，再由 Provider 归一化为业务 null；
业务终态结果断言不变。未放宽本地校验，也未增加自动模型重试。
