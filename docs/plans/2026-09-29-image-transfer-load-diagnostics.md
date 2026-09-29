# 镜像传输与导入诊断实施计划

目标：使最新部署的传输与 Docker 导入瓶颈可以从真实日志中区分。
方案：SSH 传输到受限临时文件，SHA-256 校验后独立执行有界 Docker 导入。
技术：Bash、GitHub Actions、pytest；执行采用并行子任务与独立审查。

- [x] 在 `tests/architecture/test_deploy_scripts.py` 补充传输、校验、导入顺序与失败隔离测试，先验证旧实现失败。
- [x] 修改 `scripts/upload-docker-images.sh`，落实分段日志、超时、容量检查与临时文件清理。
- [x] 更新运维需求和规格入口，运行部署脚本、两个工作流文件与 Compose 安全回归、Ruff、Shell 语法与差异检查；实际命令见审计。
- [ ] 独立审查改动；提交并快进 main，推送触发真实部署。
- [ ] 读取实际 CI／部署状态和分段日志，记录真实结果，必要时继续处理已定位的阻塞。
