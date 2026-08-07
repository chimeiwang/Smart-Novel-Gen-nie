# 《遗产猎人（迁移）》洞天风险模型生产写入执行计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将已确认的洞天高压模型、遗产两级评级制度和三个术语安全写入生产长篇 `cmshau1xt75e8ndiidsbys3ki`。

**Architecture:** 只通过生产 Skill 的 HTTPS wrapper 调用公共 CLI。更新使用写前 GET 的 CAS，术语创建复用已保存的稳定 `clientRequestId`；每条命令只执行一次并立即完整回读，任何版本、网络或字段异常都停止。

**Tech Stack:** PowerShell 5.1、InkForge production operator、InkForge long-serial public CLI、Core API CAS/幂等契约。

---

### Task 1：验证生产门禁与权威状态

**Files:**
- Read: `C:\Users\niebo\AppData\Local\Temp\inkforge-dongtian-risk-payloads.json`
- Create: `C:\Users\niebo\AppData\Local\Temp\inkforge-dongtian-planning-live.json`
- Create: `C:\Users\niebo\AppData\Local\Temp\inkforge-dongtian-lore-live.json`

- [x] **Step 1：核验生产身份**

Run:

```powershell
'{}' | & 'C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\scripts\operator.ps1' auth.whoami
```

Expected: exit code 0，`username` 严格等于 `nie`。

- [x] **Step 2：核验配置仓库 CLI registry**

Run: 从配置的 `repositoryRoot` 加载 InkForge CLI registry，统计总命令、long 命令、long mutation 和结构化写命令。

Expected: `77 / 61 / 44 / 32`。

- [x] **Step 3：重新完整读取规划与设定**

Run: 依次执行 `long.planning.get` 和 `long.lore.get`，分别写入上述 live 文件。

Expected: 世界设定 `updatedAt=2026-08-07T01:36:00.022000Z`，理事会 `updatedAt=2026-08-06T17:27:43.132000Z`，不存在“洞天”“遗产”“遗产评级”同名术语；否则停止并重新生成 Diff，不自动替换版本。

### Task 2：写入世界设定

**Files:**
- Read: `C:\Users\niebo\AppData\Local\Temp\inkforge-dongtian-risk-payloads.json`
- Create: `C:\Users\niebo\AppData\Local\Temp\inkforge-dongtian-planning-after-world.json`

- [x] **Step 1：执行一次世界设定 CAS 写入**

Run: 将 payload 第 1 项完整 JSON 送入 `long.lore.world-setting.save`。

Expected: exit code 0，Core 返回新的 `updatedAt`。

- [x] **Step 2：立即回读并逐字核对**

Run: 执行 `long.planning.get`，比较 `worldSetting.content` 与 payload 第 1 项 `content`。

Expected: 内容逐字一致、版本已推进，故事背景、作品圣经、大纲、节点和进度仍与写前快照一致。

### Task 3：写入理事会评级制度

**Files:**
- Read: `C:\Users\niebo\AppData\Local\Temp\inkforge-dongtian-risk-payloads.json`
- Create: `C:\Users\niebo\AppData\Local\Temp\inkforge-dongtian-lore-after-council.json`

- [x] **Step 1：执行一次理事会 CAS 更新**

Run: 将 payload 第 2 项完整 JSON 送入 `long.lore.faction.update`。

Expected: exit code 0，返回目标 ID `cmshbbop6v12kdc3ftcuealy6` 的新版本。

- [x] **Step 2：立即回读并逐字段核对**

Run: 执行 `long.lore.get`，按目标 ID 比较 `description`。

Expected: description 与 payload 完全一致；理事会其余字段、玄天宗和全部人物、地点、物品保持不变。

### Task 4：创建三个术语

**Files:**
- Read: `C:\Users\niebo\AppData\Local\Temp\inkforge-dongtian-risk-payloads.json`
- Create: `C:\Users\niebo\AppData\Local\Temp\inkforge-dongtian-lore-after-glossary-2.json`
- Create: `C:\Users\niebo\AppData\Local\Temp\inkforge-dongtian-lore-after-glossary-3.json`
- Create: `C:\Users\niebo\AppData\Local\Temp\inkforge-dongtian-lore-after-glossary-4.json`

- [x] **Step 1：创建“洞天”**

Run: 使用 `clientRequestId=dongtian-glossary-20260807-01-cmshau1xt75e8` 执行一次 `long.lore.glossary.create`，随后 `long.lore.get`。

Expected: 同名术语恰好 1 条，term、definition、category 与 payload 第 3 项完全一致。

- [x] **Step 2：创建“遗产”**

Run: 使用 `clientRequestId=dongtian-glossary-20260807-02-cmshau1xt75e8` 执行一次 `long.lore.glossary.create`，随后 `long.lore.get`。

Expected: 同名术语恰好 1 条，term、definition、category 与 payload 第 4 项完全一致。

- [x] **Step 3：创建“遗产评级”**

Run: 使用 `clientRequestId=dongtian-glossary-20260807-03-cmshau1xt75e8` 执行一次 `long.lore.glossary.create`，随后 `long.lore.get`。

Expected: 同名术语恰好 1 条，term、definition、category 与 payload 第 5 项完全一致。

### Task 5：全量验收与状态记录

**Files:**
- Create: `C:\Users\niebo\AppData\Local\Temp\inkforge-dongtian-planning-final.json`
- Create: `C:\Users\niebo\AppData\Local\Temp\inkforge-dongtian-lore-final.json`
- Modify: `docs/specs/2026-08-07-production-long-serial-dongtian-risk-model.md`

- [x] **Step 1：全量回拉**

Run: 完整执行 `long.novel.get`、`long.planning.get` 和 `long.lore.get`。

Expected: 小说 ID、名称正确；世界设定、理事会和三个术语全部等于确认 payload。

- [x] **Step 2：验证排除范围**

Run: 将最终规划与设定和写前快照逐字段比较，目标资源只允许内容和版本变化，三个术语只允许新增目标项。

Expected: 故事背景、作品圣经、大纲、节点、进度、章节、人物、地点、物品、玄天宗及其他非目标字段保持不变。

- [x] **Step 3：更新规格状态并提交本地记录**

Modify: 将规格状态改为“生产写入完成并回读验收通过”，记录五条目标写入的最终版本或 ID。

Run:

```powershell
git add -- docs/specs/2026-08-07-production-long-serial-dongtian-risk-model.md docs/plans/2026-08-07-production-dongtian-risk-write.md
git commit -m '文档：记录洞天风险模型生产写入结果'
```

Expected: 工作树干净；本地提交只包含本规格和执行计划，不自动推送远端。
