# 长篇小说创建 CLI 实施计划

1. 先增加 `long.novel.create` 的命令映射、输入校验和注册表失败测试。
2. 实现独立的长篇创建 handler，固定 `long_serial`，注册为需登录的非幂等写命令。
3. 更新 CLI README 的长篇边界与命令清单。
4. 先更新两个 Operator 的契约测试，再同步其命令清单、操作流程和网络不确定恢复规则。
5. 运行 CLI 全量测试、Ruff、Mypy、Core 既有创建契约测试及两个 Skill 的验证脚本。
6. 检查 diff 和工作区边界后提交隔离分支；本轮不部署。
