# Java 旧视频死代码构建修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除已退役但仍引用消失 DTO 的旧视频 Java 源码，使最新 `main` 恢复编译并保持新 Episode 视频链完整。

**Architecture:** 把当前 Maven 编译失败作为真实红灯，以架构测试冻结“旧路由、旧后台装配、旧源码同时退场”的边界。整类删除未装配的旧 chapter-adaptation、legacy plan、旧 render 和旧 post-production，仅从仍活动的 VisualCanon 与 Episode 模拟器中移除旧方法。

**Tech Stack:** Java 21、Spring Boot 4.1.1、Maven、JUnit 5、Python 架构测试（仅仓库静态门禁）

---

### Task 1: 冻结旧视频源码退役门禁

**Files:**
- Modify: `tests/architecture/test_video_legacy_retirement.py`
- Test: `tests/architecture/test_video_legacy_retirement.py`

- [ ] **Step 1: 增加失败的源码缺失断言**

在现有 P4 退役测试中增加 `RETIRED_JAVA_SOURCES`，至少覆盖四组入口：

```python
RETIRED_JAVA_SOURCES = (
    "video/application/VideoAdaptationService.java",
    "video/application/LegacyVideoPlanService.java",
    "video/application/VideoRenderService.java",
    "video/application/VideoPostProductionService.java",
    "agentgateway/VideoAdaptationAgentSubmitter.java",
)


def test_retired_java_video_sources_are_physically_removed() -> None:
    java_root = ROOT / "apps/core-api-java/src/main/java/cn/inkforge/core"
    leftovers = [path for path in RETIRED_JAVA_SOURCES if (java_root / path).exists()]
    assert leftovers == []
```

- [ ] **Step 2: 运行测试并确认红灯**

Run: `uv run pytest tests/architecture/test_video_legacy_retirement.py -q`

Expected: FAIL，列出仍存在的旧 Java 源码；不得因测试失败改回旧 OpenAPI DTO。

- [ ] **Step 3: 提交红灯测试**

```powershell
git add -- tests/architecture/test_video_legacy_retirement.py
git commit -m "测试：冻结旧视频 Java 源码退役边界"
```

### Task 2: 删除未装配的旧章节改编与旧计划实现

**Files:**
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/application/VideoAdaptationDecisionStore.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/application/VideoAdaptationRepository.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/application/VideoAdaptationService.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/application/VideoAdaptationTaskStore.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/application/VideoAdaptationTaskSubmitter.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/application/VideoAdaptationTaskDispatcher.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/application/LegacyVideoPlanProgress.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/application/LegacyVideoPlanService.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/application/LegacyVideoPlanStore.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/application/LegacyVideoPlanDispatcher.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/application/LegacyVideoPlanDispatchStore.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/domain/VideoAdaptationPlans.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/domain/SeedancePromptCompiler.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/JooqVideoAdaptationDecisionStore.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/JooqVideoAdaptationReadModel.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/JooqVideoAdaptationRepository.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/JooqVideoAdaptationTaskStore.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/JooqVideoPlanMaterializer.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/JooqLegacyVideoPlanStore.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/JooqLegacyVideoPlanDispatchStore.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/LegacyVideoPlanProgressCodec.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/VideoAdaptationTaskPayload.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/ProviderVideoAdaptationTaskSubmitter.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/DurableVideoAdaptationRun.java`
- Delete: matching dedicated tests under `apps/core-api-java/src/test/java/cn/inkforge/core/video/**`
- Modify: `apps/core-api-java/src/main/java/cn/inkforge/core/agentgateway/AgentGatewayConfiguration.java`

- [ ] **Step 1: 删除未被当前 Spring 配置装配的旧类型和专属测试**

使用精确文件清单删除上述类型及只测试这些类型的 `VideoAdaptation*Test`、`LegacyVideoPlan*Test`、
`SeedancePromptCompilerTest`、`VideoAdaptationPlansTest` 和 `VideoAdaptationFixtures`。保留所有
`VideoEpisode*` 类型与测试。

- [ ] **Step 2: 删除 AgentGateway 中旧提交器 Bean**

从 `AgentGatewayConfiguration` 删除只返回 `VideoAdaptationTaskSubmitter` 的方法和 import；保留新 Episode
V2 执行与 provider media 所需的 Agent 端口。

- [ ] **Step 3: 扫描旧类型是否仍有活动引用**

Run:

```powershell
rg -n "VideoAdaptation(Service|TaskStore|TaskSubmitter)|LegacyVideoPlan|SeedancePromptCompiler" apps/core-api-java/src/main apps/core-api-java/src/test
```

Expected: 0 个活动源码命中。

- [ ] **Step 4: 提交旧章节改编清理**

```powershell
git add -- apps/core-api-java tests/architecture/test_video_legacy_retirement.py
git commit -m "修复：删除已退役的视频章节改编实现"
```

### Task 3: 删除旧 render 与旧 post-production 实现

**Files:**
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/application/VideoRenderClaim.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/application/VideoRenderReconciler.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/application/VideoRenderRepository.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/application/VideoRenderService.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/JooqVideoRenderRepository.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/VideoRenderManifestCodec.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/application/VideoPostProductionReconciler.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/application/VideoPostProductionRepository.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/application/VideoPostProductionService.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/JooqVideoPostProductionRepository.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/JooqVideoPostProductionReadModel.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/JooqVideoTimelineRepository.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/JooqVideoExportRepository.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/VideoPostProductionCommands.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/VideoPostProductionContext.java`
- Delete: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/VideoPostProductionDatabaseAccess.java`
- Delete: matching old `VideoRender*Test`, `JooqVideoRenderRepositoryTest`, `VideoPostProduction*Test`

- [ ] **Step 1: 删除旧实现和专属测试**

保留 `VideoEpisodeRender*`、`VideoEpisodePostProduction*`、新 Take／Mix／Export 代码及测试。

- [ ] **Step 2: 验证旧名只剩历史文档**

Run:

```powershell
rg -n "VideoRender(Claim|Service|Repository|Reconciler)|VideoPostProduction(Service|Repository|Reconciler)" apps/core-api-java/src/main apps/core-api-java/src/test
```

Expected: 只允许下一任务需要从活动模拟器中移除的旧重载；不得命中新旧公共入口。

- [ ] **Step 3: 提交旧生成与后期清理**

```powershell
git add -- apps/core-api-java
git commit -m "修复：删除已退役的视频生成与后期实现"
```

### Task 4: 收窄仍活动的 VisualCanon 与模拟器接口

**Files:**
- Modify: `apps/core-api-java/src/main/java/cn/inkforge/core/video/application/VideoVisualCanonService.java`
- Modify: `apps/core-api-java/src/main/java/cn/inkforge/core/video/application/VideoVisualCanonRepository.java`
- Modify: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/JooqVideoVisualCanonRepository.java`
- Modify: `apps/core-api-java/src/main/java/cn/inkforge/core/video/application/VideoRenderSimulator.java`
- Modify: `apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/FfmpegVideoRenderSimulator.java`
- Modify: `apps/core-api-java/src/test/java/cn/inkforge/core/video/application/VideoEpisodeRenderReconcilerTest.java`
- Modify: `apps/core-api-java/src/test/java/cn/inkforge/core/video/infrastructure/FfmpegVideoRenderSimulatorTest.java`

- [ ] **Step 1: 让保留测试只实现 Episode-native 模拟器方法**

测试替身只保留：

```java
@Override
public SimulatedVideo render(VideoEpisodeRenderClaim claim) {
    return simulatedVideo;
}
```

删除 `render(VideoRenderClaim)` 的 override 和旧 claim 夹具。

- [ ] **Step 2: 删除活动类中的旧章节方法**

从 VisualCanon service/repository 删除 `saveShotReferences` 旧章节改编方法及其 jOOQ 辅助查询；保留项目级
VisualCanon 和新 Episode 基线读取。从模拟器 interface/FFmpeg 实现删除 `VideoRenderClaim` 重载，仅保留
`VideoEpisodeRenderClaim`。

- [ ] **Step 3: 运行最小编译红绿验证**

Run: `.\mvnw.cmd --batch-mode --no-transfer-progress -pl apps/core-api-java -am '-DskipTests' compile`

Expected: reactor 4 个模块 `BUILD SUCCESS`，不再出现缺失旧视频 DTO。

- [ ] **Step 4: 运行视频与架构定向测试**

Run:

```powershell
.\mvnw.cmd --batch-mode --no-transfer-progress -pl apps/core-api-java -am '-Dtest=VideoEpisode*Test,FfmpegVideoRenderSimulatorTest' test
uv run pytest tests/architecture/test_video_legacy_retirement.py -q
```

Expected: 全部 PASS；没有恢复旧接口或数据库写入。

- [ ] **Step 5: 提交活动接口收口**

```powershell
git add -- apps/core-api-java tests/architecture/test_video_legacy_retirement.py
git commit -m "重构：收窄视频模拟器与视觉设定边界"
```

### Task 5: 完整验证并记录构建修复

**Files:**
- Modify: `docs/audits/2026-09-10-video-legacy-retirement-p4.md`

- [ ] **Step 1: 运行完整 Maven 验证**

Run: `.\mvnw.cmd --batch-mode --no-transfer-progress verify`

Expected: `BUILD SUCCESS`；记录各模块测试数和跳过的外部环境测试。

- [ ] **Step 2: 更新审计事实**

在 P4 审计中补充当前提交的源码物理清理、未执行数据库 DDL、Maven 结果和仍保留的新 Episode／共享媒体范围。

- [ ] **Step 3: 检查并提交**

```powershell
git diff --check
git add -- docs/audits/2026-09-10-video-legacy-retirement-p4.md
git commit -m "审计：记录旧视频 Java 源码清理结果"
```
