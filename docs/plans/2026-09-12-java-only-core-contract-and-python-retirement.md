# Java-only Core 契约与 Python 退役实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Java 成为 Core、公共接口维护和普通 CLI 的唯一实现，删除 Python Core／CLI，同时保持 Python Agent 独立运行。

**Architecture:** 以提交的 OpenAPI 3.0.3 完整契约为单一来源，确定性生成公共投影、Java API/DTO、Java CLI client 与 TypeScript client；Java 运行时路由测试验证全部 207 个操作。迁移所有构建和运维消费者后，再物理删除 Python Core/CLI，保留 Agent 与语言中立 golden fixtures。

**Tech Stack:** Java 21、Spring Boot 4.1.1、Maven、OpenAPI Generator、Node.js、openapi-typescript、JUnit 5、Python Agent、Docker Compose

---

### Task 1: 建立 canonical Core OpenAPI 与投影器

**Files:**
- Create: `contracts/core/openapi.json`
- Create: `contracts/core/public-openapi.json`
- Create: `scripts/build_core_openapi.mjs`
- Create: `scripts/build_core_openapi.test.mjs`
- Modify: `package.json`
- Source: `contracts/core/full-openapi-java-baseline.json`
- Source: `contracts/core/route-inventory.json`

- [ ] **Step 1: 为投影规则写 Node 红灯测试**

测试必须构造 public、internal 与 provider media 三类操作，并断言只有 public 进入投影：

```javascript
test("公共投影按 exposure 排除内部和 provider media", () => {
  const projected = projectPublicOpenApi(fixture);
  assert.deepEqual(Object.keys(projected.paths), ["/api/v1/public"]);
  assert.equal(projected.paths["/api/v1/public"].get.operationId, "get_public");
});
```

另写重复 operationId、缺失 `x-inkforge-exposure`、非 LF 输出与 `--check` 漂移测试。

- [ ] **Step 2: 运行 Node 测试并确认红灯**

Run: `node --test scripts/build_core_openapi.test.mjs`

Expected: FAIL，原因是 `build_core_openapi.mjs` 尚不存在。

- [ ] **Step 3: 实现确定性投影器**

导出以下纯函数并提供 CLI：

```javascript
export function projectPublicOpenApi(full) { /* 返回 exposure=public 的稳定副本 */ }
export function validateCoreOpenApi(full) { /* 校验 operationId、分类和 method/path 唯一性 */ }
export function stableJson(value) { return `${JSON.stringify(value, null, 2)}\n`; }
```

CLI 默认写 `contracts/core/public-openapi.json`，`--check` 比较规范化 LF 内容且不修改文件。

- [ ] **Step 4: 提升现有 Java 契约并带入 exposure 元数据**

以 `full-openapi-java-baseline.json` 为语义源创建 `openapi.json`。按旧 `route-inventory.json` 的
`method + path` 合并 `x-inkforge-exposure`、`x-inkforge-authentication`、`x-inkforge-product-module`、
`x-inkforge-response-kind`、`x-inkforge-transaction` 和副作用；provider media 路径必须标为
`provider_media`，不能因 `/api/v1/` 前缀进入公共投影。

- [ ] **Step 5: 生成公共投影并验证数量**

Run:

```powershell
node scripts/build_core_openapi.mjs
node scripts/build_core_openapi.mjs --check
node --test scripts/build_core_openapi.test.mjs
```

Expected: public 141 路径/182 操作，full 166 路径/207 操作，internal 24，provider media 1。

- [ ] **Step 6: 提交 canonical 契约**

```powershell
git add -- contracts/core/openapi.json contracts/core/public-openapi.json scripts/build_core_openapi.mjs scripts/build_core_openapi.test.mjs package.json
git commit -m "功能：建立 Java Core 唯一 OpenAPI 契约"
```

### Task 2: 切换 Java 与 TypeScript 生成链

**Files:**
- Modify: `apps/core-api-java/pom.xml`
- Modify: `packages/service-contracts-java/pom.xml`
- Modify: `tools/inkforge-cli-java/pom.xml`
- Modify: `scripts/generate_api_client.mjs`
- Modify: `packages/api-client/src/generated/schema.d.ts`
- Test: `scripts/build_core_openapi.test.mjs`

- [ ] **Step 1: 增加“不启动 Python”的生成红灯测试**

测试读取 `scripts/generate_api_client.mjs` 并断言不存在活动的 `child_process`、`uv`、`python`、
`export_openapi.py` 或 `inkforge_core` 调用，同时断言输入为 `contracts/core/public-openapi.json`。

- [ ] **Step 2: 运行并确认红灯**

Run: `node --test scripts/build_core_openapi.test.mjs`

Expected: FAIL，命中当前 `execFileSync` 和 Python exporter。

- [ ] **Step 3: 切换全部生成输入**

三个 Maven module 分别改为 full canonical 或 public projection：

```xml
<inputSpec>${project.basedir}/../../contracts/core/openapi.json</inputSpec>
```

Java CLI 使用：

```xml
<inputSpec>${project.basedir}/../../contracts/core/public-openapi.json</inputSpec>
```

TypeScript 生成器直接 `readFileSync(publicOpenApiPath, "utf8")`，只对内存副本处理数字 discriminator。

- [ ] **Step 4: 运行生成与漂移检查**

Run:

```powershell
npm run api:generate
npm run api:check
.\mvnw.cmd --batch-mode --no-transfer-progress -pl packages/service-contracts-java,apps/core-api-java,tools/inkforge-cli-java -am generate-sources
```

Expected: 无 Python 进程；TS 生成结果语义不变；Maven 生成成功。

- [ ] **Step 5: 提交生成链切换**

```powershell
git add -- apps/core-api-java/pom.xml packages/service-contracts-java/pom.xml tools/inkforge-cli-java/pom.xml scripts/generate_api_client.mjs packages/api-client/src/generated/schema.d.ts scripts/build_core_openapi.test.mjs
git commit -m "重构：将客户端生成切换到 Java Core 契约"
```

### Task 3: 建立 Java 207 路由双向覆盖门禁

**Files:**
- Create: `apps/core-api-java/src/test/java/cn/inkforge/core/contract/CoreRouteCoverageTest.java`
- Modify: `apps/core-api-java/src/test/java/cn/inkforge/core/GeneratedApiCoverageTest.java`
- Modify: `contracts/core/route-inventory.json`
- Modify: `contracts/core/internal-endpoints.json`
- Modify: `scripts/build_core_openapi.mjs`

- [ ] **Step 1: 写运行时路由覆盖红灯测试**

`CoreRouteCoverageTest` 从 canonical 读取 `method/path/operationId/exposure/produces/consumes`，从
`RequestMappingHandlerMapping` 读取实际 Java handler，规范化 `{variable}` 后比较集合：

```java
assertThat(actualRoutes)
        .containsExactlyInAnyOrderElementsOf(contractRoutes);
assertThat(contractRoutes).hasSize(207);
assertThat(publicRoutes).hasSize(182);
assertThat(internalRoutes).hasSize(24);
assertThat(providerMediaRoutes).hasSize(1);
```

健康接口必须以手写 `HealthController` 映射进入实际集合，不允许排除；Actuator 路由必须排除在产品集合外。

- [ ] **Step 2: 运行并确认红灯**

Run: `.\mvnw.cmd -pl apps/core-api-java -am '-Dtest=CoreRouteCoverageTest' test`

Expected: FAIL，当前没有该测试或旧路由投影缺少 Java-owned 元数据。

- [ ] **Step 3: 生成 v2 路由与内部接口投影**

投影器从 canonical 扩展生成 `core-route-inventory/2.0`，每项只包含语言中立协议信息；删除
`endpointModule`、`sourceFile`、`sourceLine`、`pythonTests` 和 Python baseline commit。内部投影只包含
`exposure=internal` 的 24 项；provider media 单独保留 1 项。

- [ ] **Step 4: 删除旧 6 接口存在性伪覆盖**

将 `GeneratedApiCoverageTest` 改为只验证生成源码编译所需的特殊类型边界，路由完整性全部交给
`CoreRouteCoverageTest`，删除“179 操作”和仅检查 6 个接口名的断言。

- [ ] **Step 5: 运行契约测试**

Run:

```powershell
node scripts/build_core_openapi.mjs --check
.\mvnw.cmd -pl apps/core-api-java -am '-Dtest=CoreRouteCoverageTest,GeneratedApiCoverageTest' test
```

Expected: Java 实际路由与 canonical 的 207 项完全一致。

- [ ] **Step 6: 提交路由覆盖**

```powershell
git add -- apps/core-api-java/src/test/java/cn/inkforge/core/contract/CoreRouteCoverageTest.java apps/core-api-java/src/test/java/cn/inkforge/core/GeneratedApiCoverageTest.java contracts/core/route-inventory.json contracts/core/internal-endpoints.json scripts/build_core_openapi.mjs
git commit -m "测试：建立 Java Core 全路由契约门禁"
```

### Task 4: 迁移 CLI registry 并移除 Python parity

**Files:**
- Modify: `contracts/cli/command-registry.json`
- Modify: `tools/inkforge-cli-java/src/main/java/cn/inkforge/cli/registry/CommandSpec.java`
- Modify: `tools/inkforge-cli-java/src/main/java/cn/inkforge/cli/registry/CommandCatalog.java`
- Modify: `tools/inkforge-cli-java/src/test/java/cn/inkforge/cli/registry/CommandCatalogTest.java`
- Modify: `tools/inkforge-cli-java/src/test/java/cn/inkforge/cli/runtime/CrossLanguageCliInputParityTest.java`
- Replace: `tests/architecture/test_cli_migration_baseline.py`
- Delete: `scripts/export_cli_migration_baseline.py`

- [ ] **Step 1: 写 Java-owned registry 红灯测试**

把 schema 期望改为 `inkforge-cli-command-registry/2.0`，字段集合删除 `pythonHandler`，`source` 固定为
`tools/inkforge-cli-java`，并继续断言 152 个命令和 handler 双向一致。

- [ ] **Step 2: 运行并确认红灯**

Run: `.\mvnw.cmd -pl tools/inkforge-cli-java -am '-Dtest=CommandCatalogTest' test`

Expected: FAIL，当前注册表仍为 1.0 且含 `pythonHandler`。

- [ ] **Step 3: 升级 registry 与 Java records**

`CommandSpec` 改为：

```java
public record CommandSpec(
        String name,
        InputMode inputMode,
        OutputMode outputMode,
        FileOutput fileOutput,
        boolean mutation,
        boolean requiresIdentity,
        boolean requiresClientRequestId) {}
```

`CommandCatalog` 的允许字段、解析和错误文案同步删除 Python handler。

- [ ] **Step 4: 把跨语言测试改为 Java 夹具回归**

删除 `runPythonProbe`、Python executable 和 `cli_parity_probe.py` 依赖，保留同一批输入夹具对 Java CLI 的
退出码、stdout/stderr、联网前校验和 Unicode 完整性断言。

- [ ] **Step 5: 运行 CLI 全量验证**

Run: `.\mvnw.cmd -pl tools/inkforge-cli-java -am test`

Expected: 152 个 registry 项与 152 个 Java handler 一一对应；Artifact revision 测试通过。

- [ ] **Step 6: 提交 registry 接管**

```powershell
git add -- contracts/cli/command-registry.json tools/inkforge-cli-java tests/architecture/test_cli_migration_baseline.py scripts/export_cli_migration_baseline.py
git commit -m "重构：由 Java CLI 接管命令注册表"
```

### Task 5: 迁移开发、schema、镜像和恢复入口

**Files:**
- Modify: `scripts/dev.mjs`
- Modify: `scripts/schema_fingerprint.sh`
- Replace: `scripts/recovery_drill.sh`
- Modify: `scripts/deploy-production.sh`
- Modify: `scripts/rollback_drill.sh`
- Modify: `scripts/upload-docker-images.sh`
- Modify: `infra/docker/core-api.Dockerfile`
- Delete: `infra/compose.python-core-rollback.yaml`
- Modify: `.github/workflows/build.yml`
- Modify: `.github/workflows/token-usage-details-migration.yml`
- Modify: `tests/architecture/test_local_development.py`
- Modify: `tests/architecture/test_compose_security.py`
- Modify: `tests/architecture/test_deploy_scripts.py`
- Modify: `tests/architecture/test_rollback_drill.py`
- Modify: `tests/architecture/test_github_workflow.py`

- [ ] **Step 1: 先把架构测试改为 Java-only 期望**

断言：开发 Core 命令为 Java；Dockerfile 不复制 `apps/core-api`；部署／回滚不分支到 Python runtime；CI 的
Core schema guard 只调用 `/usr/local/bin/inkforge-schema-guard`；任何活动脚本不得导入 `inkforge_core`。

- [ ] **Step 2: 运行并确认红灯**

Run:

```powershell
uv run pytest tests/architecture/test_local_development.py tests/architecture/test_compose_security.py tests/architecture/test_deploy_scripts.py tests/architecture/test_rollback_drill.py tests/architecture/test_github_workflow.py -q
```

Expected: FAIL，精确命中当前 Uvicorn Core、Python schema 路径和 rollback overlay。

- [ ] **Step 3: 切换开发和镜像输入**

`scripts/dev.mjs` 用 Maven Java 进程启动 Core，Agent 继续使用 Uvicorn；Core 环境继续移除供应商密钥。
Dockerfile 只复制 Java schema resources，不复制 Python Core 文件。上传镜像输入列表同步删除 Python schema。

- [ ] **Step 4: 删除 Python 回滚分支**

部署和回滚只接受带 `cn.inkforge.core.runtime=java` 且 V2-aware 的 Core 镜像；删除 Python 健康 overlay、
Python schema guard 和 `verify_python_rollback_stack`。失败恢复仍按切换前实际不可变 Web/Core/Agent 镜像组合，
不执行 DDL rollback。

- [ ] **Step 5: 迁移 recovery 与 workflow schema guard**

`recovery_drill.sh` 改为调用 Java Core 已有运维／只读检查入口；若当前 Java 没有等价恢复审计命令，先新增
具名 Java command 和 JUnit，再替换脚本。GitHub workflow 中容器内检查统一调用
`/usr/local/bin/inkforge-schema-guard`。

- [ ] **Step 6: 运行定向架构和 shell 语法测试**

Run:

```powershell
uv run pytest tests/architecture/test_local_development.py tests/architecture/test_compose_security.py tests/architecture/test_deploy_scripts.py tests/architecture/test_rollback_drill.py tests/architecture/test_github_workflow.py -q
bash -n scripts/schema_fingerprint.sh scripts/recovery_drill.sh scripts/deploy-production.sh scripts/rollback_drill.sh scripts/upload-docker-images.sh
```

Expected: 全部 PASS，活动脚本无 Python Core 路径。

- [ ] **Step 7: 提交运行链迁移**

```powershell
git add -- scripts infra .github tests/architecture
git commit -m "运维：移除 Python Core 活动入口"
```

### Task 6: 删除 Python Core 并收敛 Python workspace

**Files:**
- Delete: all tracked files under `apps/core-api/`
- Delete: `scripts/export_openapi.py`
- Delete: `scripts/export_core_migration_baseline.py`
- Delete: `scripts/export_schema_contract.py`
- Delete: `apps/core-api-java/src/test/java/cn/inkforge/core/compatibility/PythonCoreProcess.java`
- Delete: `apps/core-api-java/src/test/java/cn/inkforge/core/compatibility/CoreBehaviorDifferentialTest.java`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: Core-dependent tests under `tests/`

- [ ] **Step 1: 增加无 Python Core 静态门禁**

在仓库布局测试中断言 `apps/core-api` 不存在，活动文件不得包含 `inkforge_core` import/start；历史文档路径
明确排除，不把 `apps/core-api-java` 子串误报为旧目录。

- [ ] **Step 2: 运行并确认红灯**

Run: `uv run pytest tests/architecture/test_repository_layout.py -q`

Expected: FAIL，报告 Python Core 目录和活动引用。

- [ ] **Step 3: 先迁移测试消费者**

把 `tests/test_service_auth_directions.py` 改为直接验证共享 `inkforge_service_auth`；把 Durable V2、E2E、视频和
schema 测试的 contract 路径改为 Java resources/canonical；删除只能启动 Python Core 的差异用例。

- [ ] **Step 4: 删除 Python Core 与 exporter**

通过 Git 跟踪清单生成精确删除 patch，删除 `apps/core-api/**` 和三个 Core exporter；不得对原主工作区执行
`clean`、`reset` 或全量 stash。

- [ ] **Step 5: 收敛 workspace 并重新锁定**

从 `pyproject.toml` workspace/testpaths/mypy 删除 Core，运行：

```powershell
uv lock
uv sync --frozen --all-packages --group dev
```

Expected: 环境只安装 Agent、service-contracts、service-auth；不再安装 `inkforge-core-api`。

- [ ] **Step 6: 运行保留 Python 全量验证**

Run:

```powershell
uv run pytest
uv run ruff check .
uv run mypy apps/agent-service/src packages/service-contracts/src packages/service-auth/src
```

Expected: 全部 PASS；Agent 不导入 Core 或数据库驱动。

- [ ] **Step 7: 提交 Python Core 删除**

```powershell
git add -- apps/core-api scripts pyproject.toml uv.lock tests apps/core-api-java/src/test/java/cn/inkforge/core/compatibility
git commit -m "重构：彻底移除 Python Core"
```

### Task 7: 删除 Python CLI 并保持 Java 152 命令

**Files:**
- Delete: all tracked files under `tools/inkforge-cli/`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `.github/workflows/build.yml`
- Modify: `tools/inkforge-cli-java/README.md`
- Modify: `tests/architecture/test_repository_layout.py`

- [ ] **Step 1: 验证原工作区 revision 能力已在 Java 存在**

Run:

```powershell
rg -n "INVALID_ARTIFACT_REVISION|revision" tools/inkforge-cli-java/src/main/java/cn/inkforge/cli/commands/LongReadCommands.java tools/inkforge-cli-java/src/test/java/cn/inkforge/cli/commands/LongReadCommandsTest.java
```

Expected: Java handler、正整数 query 和联网前非法值测试全部存在；不复制原工作区 Python 改动。

- [ ] **Step 2: 删除 Python CLI 跟踪文件**

通过精确删除 patch 删除 `tools/inkforge-cli/**`，并从 workspace、pytest、CI、文档入口删除 Python CLI。
原主工作区三项未提交文件保持原样，不在该目录执行清理。

- [ ] **Step 3: 更新 Java CLI 当前说明**

README 统一写当前 152 个普通命令，说明 `long.artifact.get.revision`、Windows Credential Manager、Operator
45 命令白名单和 Python CLI 已退役；历史数量只标记为历史迁移记录。

- [ ] **Step 4: 重新锁定并验证**

Run:

```powershell
uv lock
uv sync --frozen --all-packages --group dev
.\mvnw.cmd -pl tools/inkforge-cli-java -am test
```

Expected: Python 环境无 `inkforge-cli`；Java registry/handler 152 项全绿。

- [ ] **Step 5: 提交 Python CLI 删除**

```powershell
git add -- tools pyproject.toml uv.lock .github/workflows/build.yml tests/architecture
git commit -m "重构：彻底移除 Python CLI"
```

### Task 8: 更新仓内与本机 Operator Skill

**Files:**
- Create: `tools/inkforge-cli-java/operator/run.ps1`
- Create: `tools/inkforge-cli-java/operator/configure.ps1`
- Modify: `tools/inkforge-cli-java/operator/run.sh`
- Modify: `tools/inkforge-cli-java/operator/configure.sh`
- Modify: installed local Operator Skill files under `C:/Users/niebo/.codex/skills/inkforge-short-story-operator/`
- Modify: installed production Operator Skill files under `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/`
- Test: `tools/inkforge-cli-java/src/test/java/cn/inkforge/cli/operator/OperatorMainTest.java`

- [ ] **Step 1: 按 writing-skills 规则读取并备份两份活动 Skill**

解析当前 wrapper、固定 JAR、配置目录、Credential Manager target 和 45 命令／三操作白名单。备份只包含将
修改的入口文件和 SHA 清单，不复制凭据或 token。

- [ ] **Step 2: 写 Windows wrapper 红灯测试**

断言两份 PowerShell 入口只执行 `java -jar ... operator`，拒绝 `uv`、`python`、裸 CLI 和超出白名单的命令，
且本地端点必须为回环、生产端点必须符合既有 HTTPS allowlist。

- [ ] **Step 3: 实现仓内 PowerShell 入口并更新安装 Skill**

PowerShell 使用参数数组启动 Java，不拼接 shell 命令；配置只保存 endpoint/profile，token 仍由 Java CLI 写入
Windows Credential Manager。安装 Skill 的权限和命令白名单保持不变。

- [ ] **Step 4: 构建固定 JAR 并验证 Skill**

Run:

```powershell
.\mvnw.cmd -pl tools/inkforge-cli-java -am package
& tools/inkforge-cli-java/operator/run.ps1 --help
```

随后运行两份 Skill 的帮助、configure、允许命令 dry-run、端点拒绝、未知命令拒绝和 operation 拒绝测试。

- [ ] **Step 5: 提交仓内入口**

```powershell
git add -- tools/inkforge-cli-java/operator tools/inkforge-cli-java/src/test tools/inkforge-cli-java/README.md
git commit -m "功能：将 Windows Operator 切换到 Java CLI"
```

本机 Skill 是安装状态变更，不随仓库提交；最终报告其备份位置、JAR SHA 和验证结果。

### Task 9: 更新架构决策、需求与当前事实

**Files:**
- Create: `docs/architecture-decisions/004-java-only-core-contract.md`
- Modify: `AGENTS.md`
- Modify: `DOCS.md`
- Modify: `docs/requirements/00-overview.md`
- Modify: `docs/requirements/03-ai-writing-and-agents.md`
- Modify: `docs/requirements/05-auth-billing-and-ops.md`
- Modify: `docs/specs/2026-08-24-core-java-replacement.md`
- Modify: `docs/plans/2026-08-24-core-java-tdd-replacement.md`
- Modify: `docs/specs/2026-09-01-durable-agent-v2-operator-skill-update.md`
- Modify: `README.md`

- [ ] **Step 1: 新增取代 ADR**

ADR-004 明确 canonical OpenAPI、Java-only Core/CLI、Python Agent 保留、Python Core 不再是回滚目标、无 DDL
和不从 Spring 注解反向生成契约；ADR-002/003 保留历史并链接 ADR-004。

- [ ] **Step 2: 更新仓库规则与需求**

把“公共接口先改 FastAPI/Pydantic”“Python Core 历史镜像与公共契约来源”“Python CLI 对照”改为新流程。
统一当前数量为 public 141/182、internal 24、provider media 1、普通 CLI 152；旧 148/125 等只保留为具名
历史基线。

- [ ] **Step 3: 运行文档与残留检查**

Run:

```powershell
git diff --check
rg -n "公共接口先改 FastAPI|Python Core.*契约来源|Python CLI.*契约对照" AGENTS.md DOCS.md README.md docs tools/inkforge-cli-java/README.md
```

Expected: 活动规则 0 命中；历史段落必须明确标为历史并链接 ADR-004。

- [ ] **Step 4: 提交文档迁移**

```powershell
git add -- AGENTS.md DOCS.md README.md docs tools/inkforge-cli-java/README.md
git commit -m "文档：完成 Java-only Core 与 CLI 事实切换"
```

### Task 10: 全量验证与完成审计

**Files:**
- Create: `docs/audits/2026-09-12-java-only-core-python-retirement.md`

- [ ] **Step 1: 运行静态残留门禁**

使用精确路径和 import 规则检查活动代码；允许 Python Agent、共享 Python 库和历史文档，不得把
`apps/core-api-java` 误报为旧 Core。

- [ ] **Step 2: 运行 Java、契约与 Web 全量验证**

Run:

```powershell
.\mvnw.cmd --batch-mode --no-transfer-progress verify
node --test scripts/build_core_openapi.test.mjs
npm run api:generate
npm run api:check
npm run typecheck
npm run lint
npm run test:web
npm run build
```

Expected: 全部 PASS，第二次 `api:generate` 后无生成漂移。

- [ ] **Step 3: 运行保留 Python 与部署配置验证**

Run:

```powershell
uv sync --frozen --all-packages --group dev
uv run pytest
uv run ruff check .
uv run mypy apps/agent-service/src packages/service-contracts/src packages/service-auth/src
uv run pytest tests/architecture/test_compose_security.py -q
```

Expected: 全部 PASS，环境中没有 Python Core/CLI package。

- [ ] **Step 4: 在可用时运行 Docker 隔离 smoke**

Run:

```powershell
docker compose --env-file .env.example -f infra/compose.yaml build web core-api agent-service
```

随后按仓库手册运行 Compose 健康、Java schema guard、Core→Agent POST 和视频生产开关拒绝测试。

- [ ] **Step 5: 写审计并提交**

审计逐项记录命令、退出码、测试数、跳过项、Docker 是否可用、本机 Skill 备份/JAR SHA。明确：未推送、
CI 未运行、未部署、未修改服务器数据库、未执行 P4 DDL、未做生产回归。

```powershell
git add -- docs/audits/2026-09-12-java-only-core-python-retirement.md
git commit -m "审计：记录 Python Core 与 CLI 退役验收"
```
