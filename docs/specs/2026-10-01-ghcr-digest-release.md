# GHCR 分层发布与已验证制品重试

日期：2026-10-01。状态：完整 CI 与镜像缓存发布通过；GHCR 生产直拉仍慢，本次通过明确的本机中转完成生产发布。
稳定的无人值守下载尚未验收，不以本次手动恢复代替自动部署成功。

## 背景与授权

9 月 30 日两轮完整 CI 通过，但 Core 约 387 MB 压缩镜像经 Runner 到生产 SSH 传输分别只有约
60 kB/s、37 kB/s，均在 1200 秒超时，业务修复尚未上线。用户已授权提交 main 和部署，随后要求
修复发布链路，并明确选择“没有，先验证 GHCR”。10 月 1 日生产只读实测：GHCR 官方 uv 镜像
公开层前 4 MiB 返回 206，耗时 2.97 秒、约 1.35 MiB/s；该小样本不代替私有包认证或完整发布验收。

本规格取代旧发布规格中默认通过 SSH 上传完整镜像、以及该轮不采用第三方镜像仓库的范围。
旧上传脚本保留作显式兼容入口，不在 GHCR 失败后自动回退并再次消耗漫长传输时间。

## 目标与不变量

- 保留完整 CI，只有当前仓库 main push 且 CI 成功才能发布镜像；PR 无制品发布或生产权限。
- 构建仍在 GitHub Runner，生产只拉取预构建镜像，保持单 Core、无 DDL、视频关闭和 V2 指纹检查。
- 不修改产品、模型工具、计费、正式内容或数据库；保持现有 Compose 服务、镜像本地名称、健康及回滚门禁。
- 不增加长期访问令牌：构建使用 job 级 packages:write，部署使用 packages:read；均使用短期 GITHUB_TOKEN。
- 服务器凭据仅经严格主机身份校验的 SSH 标准输入传输，存入本次 0700 临时 DOCKER_CONFIG；不进命令行、
  日志、源码、应用 .env 或常驻容器。拉取结束即清理，失败和中断也清理，不影响服务器原 Docker 凭据。

## 构建与制品

- CI 后独立发布三张 linux/amd64 镜像至固定前缀 `ghcr.io/chimeiwang/smart-novel-gen-nie`，
  对应服务 `web`、`core-api`、`agent-service`；工作流不修改包可见性。包的实际访问能力单独核实，
  不以仓库关联或默认行为推断私有；生产仍使用短期令牌认证。
- 使用各服务独立的 BuildKit 构建缓存复用基础层，保留现有 Dockerfile 的产品行为。
- 生成严格版本化 JSON 清单，字段为 `schemaVersion=1`、`repository`、`sourceSha`、`sourceRunId`、
  `images`。images 必须恰有上述三服务，每项包含 `repository`、`digest`、`imageId`、`sizeBytes`。
  digest/imageId 均为 sha256，SHA 为 40 位小写十六进制；拒绝未知字段、重复 JSON 键、仓库漂移、
  非正整数或重复服务。sizeBytes 来自构建出的实际镜像，供拉取容量门禁使用。
- 清单作为原运行不可变 artifact 保存；源码 SHA、运行 ID、固定仓库、镜像 digest 和 image ID 联合绑定。
  不允许用户输入任意 registry URL、digest 或镜像标签来取代可信清单。

## 生产拉取

- 独立接入脚本先在 Runner 校验清单，再以 SSH 传给远端；远端再次校验固定绑定及凭据结构。
  令牌视为不透明字符串，只校验非空、UTF-8 不超过 16 KiB 且无 NUL/CR/LF，不猜测前缀或字符集。
  启动失败使用固定错误码区分清单、缺失环境、令牌、用户名和 SSH 文件问题，不输出原值或异常原文。
- 对 Docker 数据目录作容量预检，使用逻辑镜像大小和安全余量；不得自动清理镜像、卷或数据腾空间。
- 顺序按 `repository@digest` 拉取三镜像，验证本地实际 image ID 和 RepoDigests；可复用已存在且准确
  匹配的镜像。全部校验完成后才打现有 `inkforge-服务:sourceSha` 标签，再执行原源码 bundle 上传和部署。
- 单张拉取及整个步骤均有限时；任何失败不得进入 `compose up`，日志明确服务、阶段及耗时。
- 保留 production environment、严格 known_hosts、非取消式 production 并发组、源码 bundle 校验、
  Java/V2/只读数据库结构门禁、smoke 和原镜像回滚。

## 独立重试

- 单独 workflow_dispatch 只接受原构建 run ID，通过 GitHub API 校验原运行属于当前仓库、固定构建工作流、
  push/main，CI 和制品发布 job 都成功；允许原 deploy 失败，不能要求原整次运行成功。
- 获取该运行唯一匹配名称且未过期的清单 artifact，交叉核对来源及全部内容；拒绝任意 artifact 注入。
- 重试仅允许 sourceSha 仍为远端 main HEAD，避免将重试隐式变成历史回滚；检出该 SHA 并复验 HEAD。
- 重试不重跑 CI、不重建镜像，使用原 digest，仍运行全部生产部署门禁并遵守同一生产并发组。

## 经实测选择的本机中转兼容路径

10 月 1 日完整镜像拉取持续采样只有约 100 KiB/s，而本机到生产的 4 MiB SSH 实测约 3.1 MiB/s。
在用户已授权修复发布链路和部署的范围内，可明确选择本机中转本轮已通过 CI 的镜像：

- 先停止唯一识别且尚未切换服务的本轮远端拉取进程，确认临时认证目录清理和生产仍健康，避免并发部署。
- 本机只拉取成功发布日志中的固定 registry digest，不重新构建；核对 CI 的 config image ID、
  OCI revision、linux/amd64，再传输归档。只能复用精确 image ID，不能用“源码未变”代替镜像身份。
- 仍使用严格 SSH、逐镜像容量预检、归档 SHA-256、远端导入后 image ID 核对和临时文件清理。
  Docker archive 导入不保证保留 RepoDigests，须用可信发布日志中的 image ID 验证导入结果，不能伪造 registry 元数据。
- 同一源码 SHA 的 Git bundle 与镜像全部就绪后，运行原生产脚本；保留锁、V2、只读结构、smoke 和回滚门禁。
- 此路径是明确执行的恢复流程，不是自动工作流的静默回退；审计分别记录 CI/发布成功、自动部署停止和实际恢复结果。

## 验收

- 行为测试覆盖清单篡改、错误来源/运行/分支/工作流、缺失失败 CI、重复键、非完整镜像集合与过期制品。
- 拉取测试覆盖已存在镜像、容量不足、单张失败/超时、digest 与 image ID 错配、全部成功后才打标、
  令牌不出现在 argv 或输出、私有临时目录及失败清理；不触碰真实应用数据。
- 架构检查覆盖 CI/发布/重试权限、PR 隔离、严格 SSH、生产并发与原部署门禁保留；相关 pytest、
  Compose 安全检查、Ruff、脚本语法和文档引用通过后，提交 main，跟踪完整 CI 和实际部署结果。
- 生产核对三服务镜像版本、健康/重启/OOM、旧版本回滚资格、视频关闭、原工具修复对应 Nginx 规则和日志。
  实际耗时、层复用、认证结果及限制记入审计；首次仓库迁移不假定旧 docker load 层一定命中下载缓存。
