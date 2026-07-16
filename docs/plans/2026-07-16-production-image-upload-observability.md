# 生产镜像上传可观测性实施计划

> 对应规范：`docs/specs/2026-07-16-production-image-upload-observability.md`

## 任务一：固定工作流超时契约

修改 `tests/architecture/test_github_workflow.py`，先断言上传步骤存在明确的 `timeout-minutes`，并断言脚本不再一次保存多张待上传镜像。运行该测试确认失败后，在 `.github/workflows/build.yml` 为上传步骤增加总超时。

## 任务二：固定脚本诊断与逐镜像契约

修改 `tests/architecture/test_deploy_scripts.py`，断言上传脚本具备：远端 Docker/容量预检、SSH 建连超时、逐镜像临时归档、低压缩级别、单镜像传输导入超时、退出清理和中文阶段日志。先运行测试确认现有脚本不满足契约。

## 任务三：实现上传脚本

修改 `scripts/upload-docker-images.sh`：

- 增加可配置且有默认值的查询超时和单镜像上传超时；
- 增加 SSH 建连超时；
- 在复用判断前执行远端 Docker 与文件系统只读预检；
- 使用 Runner 临时目录逐张生成压缩归档；
- 记录每张镜像的归档大小与各阶段耗时；
- 使用超时命令逐张传输并在远端导入；
- 使用退出陷阱清理 Runner 临时文件；
- 任一阶段失败时输出镜像名和阶段后返回非零。

## 任务四：回归验证

依次运行：

```bash
uv run --frozen pytest -p no:cacheprovider tests/architecture/test_github_workflow.py tests/architecture/test_deploy_scripts.py -q
uv run --frozen pytest -p no:cacheprovider tests/architecture/test_compose_security.py -q
uv run ruff check tests/architecture/test_github_workflow.py tests/architecture/test_deploy_scripts.py
sh -n scripts/upload-docker-images.sh scripts/deploy-production.sh
```

检查 `git diff --check` 和工作区差异，确认没有数据库结构、生产数据清理或无关文件改动。

## 任务五：发布闭环

使用中文提交信息提交当前分支，推送并创建 Pull Request。等待 Pull Request CI 成功后合并到 `main`，拉取本地 `main`，继续监控由 `main` 推送触发的生产工作流，直到成功或新的有界诊断明确指出具体失败阶段。
