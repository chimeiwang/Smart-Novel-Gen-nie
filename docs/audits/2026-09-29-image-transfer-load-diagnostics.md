# 镜像传输与导入诊断验收

日期：2026-09-29。基线：`c5f1d47ed1ff3a3fdc1261ee878147f6d73fa107`。
范围见 [规格](../specs/2026-09-29-image-transfer-load-diagnostics.md)。

## 本地验证

- 独立工作树：`C:/Users/niebo/.codex/worktrees/deploy-upload-diagnostics/inkForge`。
- 旧实现首先出现预期行为失败：没有独立 Docker 导入，阶段故障注入不能阻止旧管道成功返回。
- 脚本回归 73 项通过：非上传部分 55 项，加 UTF-8 模式补验的上传、源码上传与 quarantine 共 18 项。
- `test_github_deploy_workflow.py` 与 `test_compose_security.py` 共 72 项通过；`test_github_workflow.py` 16 项通过，总计 161 项。
- 全仓 Ruff、Bash 语法、`git diff --check` 通过；独立审查提出的工作流总时限问题已处理并复核。
- `test_quarantine_clear_rejects_waitaof_zero` 初次在 Windows 默认 GBK 解码下失败，未修改的 main 同样失败；使用 Python `-X utf8` 后通过，未改该测试或业务实现。
- 归档损坏测试使用实际 `dd`、SHA-256 与随机临时目录；SSH、Docker 和文件系统容量使用受控替身，不代表生产传输性能已验证。

使用仓库现有虚拟环境执行，命令主体如下：

```powershell
F:/code/inkForge/.venv/Scripts/python.exe -m pytest tests/architecture/test_deploy_scripts.py -k 'not upload' -q --tb=short
F:/code/inkForge/.venv/Scripts/python.exe -X utf8 -m pytest tests/architecture/test_deploy_scripts.py -k 'upload or quarantine_clear' -q --tb=short
F:/code/inkForge/.venv/Scripts/python.exe -m pytest tests/architecture/test_github_deploy_workflow.py tests/architecture/test_compose_security.py -q --tb=short
F:/code/inkForge/.venv/Scripts/python.exe -m pytest tests/architecture/test_github_workflow.py -q --tb=short
F:/code/inkForge/.venv/Scripts/python.exe -m ruff check .
bash -n scripts/upload-docker-images.sh
git diff --check
```

## 生产复测

本地验收时尚未推送；真实运行、分段耗时及发布结果需通过新一次 GitHub Actions 确认。
原运行 `36426104126` 的 1200 秒混合阶段超时仍不能单独证明网络或 Docker 导入故障。
