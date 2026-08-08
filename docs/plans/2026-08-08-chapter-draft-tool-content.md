# 正文章节草案工具内容契约修复实施计划

> **执行要求：** 使用测试驱动开发逐项完成；所有本地验证通过前不得推送或部署。

**目标：** 让 `begin_artifact_output` 原子携带完整正文，并保留旧标记格式兼容读取。

**架构：** Agent 工具 schema 将正文声明为必填参数；产物校验优先读取工具正文，仅对历史事件回退到可见文本标记。公共 API、数据库和审核状态机保持不变。

**技术栈：** Python 3.12、Pydantic、LangGraph、pytest、Ruff、Mypy。

---

### 任务一：建立失败回归

**文件：**

- 修改：`apps/agent-service/tests/tools/test_control.py`
- 修改：`apps/agent-service/tests/operations/test_artifact_contract.py`
- 修改：`apps/agent-service/tests/providers/test_fake_provider.py`

- [x] 新增断言：`begin_artifact_output` 的 JSON Schema 必须把 `content` 列入 required。
- [x] 新增断言：无正文标记但工具事件携带 `content` 时，产物校验应返回该正文。
- [x] 新增断言：Fake Provider 的正文终止工具参数必须包含完整 `content`。
- [x] 运行上述测试，确认它们因当前契约缺失而失败。

### 任务二：实现最小契约修复

**文件：**

- 修改：`apps/agent-service/src/inkforge_agents/tools/control.py`
- 修改：`apps/agent-service/src/inkforge_agents/runtime/execution.py`
- 修改：`apps/agent-service/src/inkforge_agents/operations/artifact_contract.py`
- 修改：`apps/agent-service/src/inkforge_agents/providers/fake.py`

- [x] 为 `BeginArtifactArgs` 增加必填、非空且无最大长度的 `content`。
- [x] 修改写作执行说明，要求完整正文放入工具 `content` 参数。
- [x] 产物校验优先读取工具 `content`，缺失时才回退旧标记解析。
- [x] Fake Provider 改用新正文参数。
- [x] 运行任务一测试并确认全部通过。

### 任务三：本地完整验证

**文件：**

- 验证：`apps/agent-service/tests/**`

- [x] 运行 Agent Service 全量 pytest。
- [x] 运行 `uv run ruff check apps/agent-service/src apps/agent-service/tests`。
- [x] 运行 `uv run mypy apps/agent-service/src`。
- [x] 使用本机真实模型和生产第一章只读快照运行完整 `AgentRunner`。
- [x] 把返回事件交给 `validate_artifact_submission()`，确认取得完整正文且不依赖标记。
- [x] 所有验证通过后再提交；提交前再次确认工作区只包含本计划范围内文件。

### 任务四：生产闭环

- [ ] 推送 `main` 并等待 CI、部署、容器健康与冒烟检查完成。
- [ ] 用新稳定请求 ID 启动第一章 `write_chapter`。
- [ ] 观察任务进入 `waiting_user`，完整读取正文 Artifact、复审意见和来源绑定状态。
- [ ] 不自动批准正文，等待用户针对该 Artifact 作出独立决定。
