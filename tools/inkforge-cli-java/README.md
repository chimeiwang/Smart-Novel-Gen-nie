# InkForge Java CLI

独立的 Java 21 命令行客户端，只访问 Core `/api/v1/**`；不直接调用 Agent、不连接数据库，不依赖 Spring Core。
注册表仍为 125 个命令，完整字段与 JSON/JSONL 规则见 `../inkforge-cli/README.md`。

## 构建与直接运行

在仓库根目录使用 JDK 21：

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
export PATH="$JAVA_HOME/bin:$PATH"
./mvnw -pl tools/inkforge-cli-java verify
java -jar tools/inkforge-cli-java/target/inkforge-cli.jar auth.login \
  --origin http://127.0.0.1:8000 --username <用户名>
printf '{}\n' | java -jar tools/inkforge-cli-java/target/inkforge-cli.jar auth.whoami
```

`auth.login` 只在真实 TTY 隐藏读取密码。macOS 使用 Keychain，Windows 使用 Credential Manager，无明文回退。
上述直接入口提供 125 命令；使用 Operator Skill 时必须走下面的受限入口，不能用裸 CLI 扩大其授权范围。

## macOS Skill 实际入口

2026-09-04，本机两份 Skill 已安装 shell 启动器与固定 Java JAR，配置已升为 schemaVersion 5，旧 Python
入口和测试已迁出到可恢复备份。实际入口的帮助、端点拒绝及隔离安装检查通过；完整 Maven 验证、CLI 回归、
Skill 结构检查和独立文档验收已通过，具体结果见
`../../docs/specs/2026-09-04-java-cli-operator-cutover.md`。同日已通过新版生产入口复用既有 Keychain 会话，
成功执行指定账号的 `auth.whoami`，未导出令牌。真实写作业务和 Windows 实机尚未验收；未部署服务器、
未执行数据库迁移，不表示生产 Agent V2 或问答已开放。

仓内启动器位于 `operator/local/` 与 `operator/production/`。构建 JAR 后，在仓库根目录先备份已有 Skill，
再安装对应启动器：

```bash
cli_cutover_backup=$(mktemp -d /tmp/inkforge-skill-backup.XXXXXX)
cli_local_skill="$HOME/.codex/skills/inkforge-short-story-operator"
cli_production_skill="$HOME/.codex/skills/inkforge-production-short-story-operator"
cp -R "$cli_local_skill" "$cli_cutover_backup/local-skill"
cp -R "$cli_production_skill" "$cli_cutover_backup/production-skill"
install -m 755 tools/inkforge-cli-java/operator/local/configure.sh \
  tools/inkforge-cli-java/operator/local/run.sh "$cli_local_skill/scripts/"
install -m 755 tools/inkforge-cli-java/operator/production/configure.sh \
  tools/inkforge-cli-java/operator/production/run.sh "$cli_production_skill/scripts/"
```

以上命令只复制启动器，不自动更新 Skill 说明。维护两份 Skill 时还必须同步：

- `SKILL.md` 与 `references/*.md` 中的 `configure.py` / `run.py` 全部改为 `configure.sh` / `run.sh`，
  删除启动 Python/uv 的业务示例，不留下可选旧入口。
- 配置说明改为 schemaVersion 5、固定安装包与显式重新 configure；来源 revision/未提交标记只是安装记录，
  源码仓库 HEAD 改变不会自动替换运行包，也不再仅因 HEAD 改变拒绝已安装包。
- 长篇 watcher 按 `engineVersion` 分流：V1 读取 `outcome`，V2 读取 `status/activeSteps/artifact/error`，
  V2 成功为 `completed`；协议错误停止，中断只停止观察。不能继续把所有任务都按 V1 outcome 解读。
- V2 Artifact 决定显式传 `engineVersion: 2`、当前 `expectedRevision` 与稳定 `clientRequestId`；
  approve/revise 先回读同一 revision 并核对来源。正文写作 V2 的 `editedContent[File]`、选区的
  `editedReplacement[File]` 和不可直接编辑的规划必须按权威候选类型区分，不能互换字段。
- 将旧 `scripts/configure.py`、`scripts/run.py`、`scripts/macos_cli.py`、`scripts/operator_support.py` 和旧
  `tests/test_operator.py` 迁出到上面的可恢复备份；不要在活动 Skill 中保留 Python/Java 双入口。新验证使用
  Java JUnit、仓内 shell 验证及 Skill 结构检查。
- 保持 45 命令与三种长篇 Operation 的允许集合；不因补充 V2 读取说明而开放 `answer_question`。

配置前也应备份各状态目录内原有的 `config.json`，然后分别运行：

```bash
"$HOME/.codex/skills/inkforge-short-story-operator/scripts/configure.sh" \
  --repository-root "$PWD"
"$HOME/.codex/skills/inkforge-production-short-story-operator/scripts/configure.sh" \
  --repository-root "$PWD"
```

可选 `--java-path <Java 可执行文件绝对路径>`、`--expected-username <绑定用户名>`；`--state-root <绝对路径>`
用于隔离验收，不改变该启动器固定的 origin/profile。已有配置升级保留绑定用户名；
不传新用户名不会清空原绑定。显式传入新的 `--expected-username` 可重新绑定账号，但不会替换 Keychain 会话，
后续必须核对新账号身份。配置沿用各自 Application Support 状态目录，schemaVersion 升为 5，记录 Java 路径、
来源提交及 JAR 哈希，安装固定运行包。运行不依赖原仓库后续切分支、不临时构建，也没有 Python/uv 回退。
若 `repositoryDirty=true`，包包含构建时未提交改动，不能声称仅 checkout 记录的 HEAD 就能得到同一代码；
实际安装包按 `jarSha256` 识别。

日常调用使用各 Skill 的 `scripts/run.sh`：

```bash
printf '{}\n' | "$HOME/.codex/skills/inkforge-short-story-operator/scripts/run.sh" auth.whoami
printf '{}\n' | "$HOME/.codex/skills/inkforge-production-short-story-operator/scripts/run.sh" auth.whoami
```

- 本地固定 `http://127.0.0.1:8000` / `default`；生产固定 `https://inkforge.cn` / `production`。
- Java Operator 先核对账号，再运行业务命令；只允许原 45 个命令。`long.agent.start` 仍只允许
  `plan_chapter`、`write_chapter`、`review_chapter`，不开放问答、选区改写或视频。
- 凭据仍使用 `InkForge CLI/<规范化 origin 的 SHA-256>` 与 `inkforge-token:<profile>`，没有迁移 token，
  因语言切换无需重新登录。系统若要求授权 Java 读取旧 Keychain 项，由用户确认；后端不可用返回
  `SECURE_CREDENTIAL_BACKEND_REQUIRED` / 3。先由用户解锁或确认访问后重试身份查询，仅在会话确实失效时登录。
- 本地登录先检查 readiness，再向用户索取密码；回环请求绕过代理。传输失败返回 `CORE_TRANSPORT_ERROR` / 5。
- stdin JSON、完整文件输出、JSONL 和 watcher 语义保持；停止观察不取消服务端任务。

生产入口按目标协议读取代理环境变量；固定 HTTPS 目标使用 `HTTPS_PROXY`，缺省时使用 `ALL_PROXY`，
`NO_PROXY` 可指定绕过。变量也接受小写形式，同名大小写同时存在时小写优先。`HTTP_PROXY` 不替代 HTTPS
目标的 `HTTPS_PROXY`。目前只支持无账号密码的 HTTP 代理，例如 `HTTPS_PROXY=http://127.0.0.1:7890`；
这里目标仍为 HTTPS，`http://` 描述的是代理协议。不支持 TLS 代理（`https://`）、SOCKS 或带认证的代理；
遇到这些配置明确返回 `OPERATOR_PROXY_UNSUPPORTED` / 2，不无声改为直连。这不是对旧 Python 代理能力的全量复刻。

## 验证范围与兼容保留

CLI 模块验证使用 `./mvnw -pl tools/inkforge-cli-java verify`，提交前还运行根目录完整 `./mvnw verify`。
现有共享 fixture 直接比较 Python/Java 的 125 命令最小输入、错误信封、代表成功请求、文件字节及全部 watcher；
Operator 的 JUnit 注入模拟 Core 与凭据，验证双环境绑定、配置升级、账号预检、允许集合、TTY、凭据和传输错误。
另用真实 JAR/shell 进程验证隔离安装、无 Python/uv 启动、无 profile、未授权命令、origin 拒绝和包校验：

```bash
tools/inkforge-cli-java/operator/test-launchers.sh "$PWD" "$JAVA_HOME/bin/java"
```

该脚本自动使用隔离配置并清理自身临时目录，不读取真实账号凭据、不联网；它不代表真实 JAR 已完成模拟 Core
业务全链。另行完成的生产 `auth.whoami` 只证明 Java 入口、既有 Keychain 会话与真实身份接线；不能据此宣称
真实写作业务、Agent V2 上线或 Windows 实机通过。测试结果记录在切换 spec。

`tools/inkforge-cli` 的 Python 源码和差异测试继续保留为兼容对照。它不再是新版 macOS Skill 的执行链；
保留 Python Agent、共享 Python 契约和旧 Core 回滚代码也不影响 Java CLI 独立运行。

章节规划 V2 沿用 `long.agent.start` 的 `plan_chapter` 及既有观察/草案决定命令，完整输入示例、
`waiting_user`/`completed` 区别、返工和禁止编辑字段见
`../../docs/specs/2026-09-04-durable-chapter-planning.md`。这条链已通过本分支的隔离 Fake 验收，不代表服务器已启用。

正文写作 V2 的本轮变更允许 `long.artifact.approve` 使用 `editedContent` 或 `editedContentFile` 采用完整
用户编辑正文；命令仍为 125 个，Skill 仍为 45 个。详情必须先通过 `long.artifact.get` 的 `revision` 精确读取，
决定继续使用 `expectedRevision`；规划不能直接编辑，选区仍只接受 replacement。完整示例、类型限制和
Skill 更新清单见 `../../docs/specs/2026-09-01-durable-agent-v2-operator-skill-update.md` 的正文编辑专节。
本轮完整验证后已重新安装本机两份固定 JAR，SHA-256 均为
`4e6a74f70a7ec5137534e31f0d0c2745966052d98592f4fafd355d32b57e5ec0`；原包和配置有可恢复备份，
完整来源记录见正文写作 spec。服务器仍未开放正文 V2；普通 Web 聊天迁移的当前源码状态见下节，不能把本机安装
或此前生产身份验证成功当作服务器业务已生效。

## 自然入口与 Skill 说明更新

当前分支的 `long.agent.start` 增加 `inputMode=natural`，`long.task.resume` 增加明确的
`inputMode=clarification`；命令总数仍为 125，完整 JSON 示例及澄清 JSONL 见 `../inkforge-cli/README.md`
的自然请求专节。自然消息新建 Run，回答绑定当前 `decisionStepId/expectedRevision`；草案返工仍走
`long.artifact.revise`。V1 显式 resume 保留，Python Core 回滚镜像拒绝新自然/澄清请求。

本轮只改仓内实现，没有更新前文已安装固定 JAR、两份活动 Skill 或服务器。后续需要更新 Skill 文本时：

- 在 `SKILL.md` 和命令参考中写明：底层 CLI 存在新模式，但 Operator 不授权；45 命令和
  `plan_chapter/write_chapter/review_chapter` 三种显式 Operation 保持不变。
- `long.agent.start` / `long.task.resume` 中禁止携带任何 `inputMode`；仓内新版 Operator 直接拒绝，不能
  通过同时附带允许的 Operation 规避，也不能改走裸 CLI。
- watcher 识别 `waitReason=clarification` 与完整 `prompt/decisionStepId/revision/data`，不得访问不存在的
  `artifactId`，不得自动用旧 resume 或 Artifact revise 回答；受限 Skill 遇此状态应展示问题并报告范围限制。
- 将“源码已实现”“固定 JAR 已安装”“对应 Core 已验收”分别记录；只有明确要求升级安装包时，才执行前文
  备份、构建与 configure 流程。本文不授权自动安装或扩充 Skill 允许范围。

Java CLI 的输入映射、watcher 与双环境 Operator 拒绝模式有定向 JUnit；Web、Python对照及跨进程验收结果
以 `../../docs/specs/2026-09-04-durable-natural-language-entry.md` 为准，不把单测当真实账号或生产验收。
