# 生产长篇设定一次性浏览器迁移 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不修改 InkForge 代码、数据库结构或源作品的前提下，通过生产 CLI 完整读取和生产 Web UI 写入，把《遗产猎人》除大纲、剧情推进、正文与运行历史外的全部设定复制到新长篇项目。

**Architecture:** 生产 Core 始终是权威状态。先用固定 HTTPS wrapper 把源项目完整导出到本地临时目录，再通过已登录的生产 Web UI 按实体依赖顺序创建目标数据，最后重新用 wrapper 导出目标项目并执行字段、数量和引用核对。所有写入只作用于新项目；源项目全程只读。

**Tech Stack:** PowerShell、InkForge production wrapper、InkForge 公共 `/api/v1/**`、Codex 浏览器控制、JSON/SHA-256。

---

### Task 1: 固定源数据快照

**Files:**
- Create: `tmp/production-long-serial-settings-migration-cmnhec5rb0000tx6g0jd0myl2/source-novel.json`
- Create: `tmp/production-long-serial-settings-migration-cmnhec5rb0000tx6g0jd0myl2/source-planning.json`
- Create: `tmp/production-long-serial-settings-migration-cmnhec5rb0000tx6g0jd0myl2/source-lore.json`
- Create: `tmp/production-long-serial-settings-migration-cmnhec5rb0000tx6g0jd0myl2/source-resources.json`

- [ ] **Step 1: 创建精确的本地输出目录**

Run:

```powershell
$migrationRoot = Resolve-Path 'tmp'
$migrationRoot = Join-Path $migrationRoot 'production-long-serial-settings-migration-cmnhec5rb0000tx6g0jd0myl2'
New-Item -ItemType Directory -Path $migrationRoot -Force | Out-Null
$migrationRoot = (Resolve-Path $migrationRoot).Path
```

Expected: `$migrationRoot` 位于 `F:\code\inkForge\tmp\` 下，不删除或覆盖其他目录。

- [ ] **Step 2: 核验生产身份**

Run:

```powershell
$operator = 'C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\scripts\operator.ps1'
'{}' | & $operator auth.whoami
```

Expected: `ok=true` 且 `username=nie`；否则停止。

- [ ] **Step 3: 完整导出源项目四组权威数据**

Run:

```powershell
$sourceNovelId = 'cmnhec5rb0000tx6g0jd0myl2'
@{ novelId = $sourceNovelId; outputFile = (Join-Path $migrationRoot 'source-novel.json') } |
  ConvertTo-Json -Compress | & $operator long.novel.get
@{ novelId = $sourceNovelId; outputFile = (Join-Path $migrationRoot 'source-planning.json') } |
  ConvertTo-Json -Compress | & $operator long.planning.get
@{ novelId = $sourceNovelId; outputFile = (Join-Path $migrationRoot 'source-lore.json') } |
  ConvertTo-Json -Compress | & $operator long.lore.get
@{ novelId = $sourceNovelId; outputFile = (Join-Path $migrationRoot 'source-resources.json') } |
  ConvertTo-Json -Compress | & $operator long.resources.get
```

Expected: 四条命令均为 `ok=true`，每个响应给出 `resultFile`，四个文件均为完整 UTF-8 JSON。

- [ ] **Step 4: 读取快照并记录数量与哈希**

Run:

```powershell
$sourceNovel = Get-Content -LiteralPath (Join-Path $migrationRoot 'source-novel.json') -Raw -Encoding utf8 | ConvertFrom-Json
$sourcePlanning = Get-Content -LiteralPath (Join-Path $migrationRoot 'source-planning.json') -Raw -Encoding utf8 | ConvertFrom-Json
$sourceLore = Get-Content -LiteralPath (Join-Path $migrationRoot 'source-lore.json') -Raw -Encoding utf8 | ConvertFrom-Json
$sourceResources = Get-Content -LiteralPath (Join-Path $migrationRoot 'source-resources.json') -Raw -Encoding utf8 | ConvertFrom-Json
[pscustomobject]@{
  name = $sourceNovel.name
  writingBibleMissing = $null -eq $sourcePlanning.writingBible
  characters = @($sourceLore.characters).Count
  factions = @($sourceLore.factions).Count
  locations = @($sourceLore.locations).Count
  items = @($sourceLore.items).Count
  glossaries = @($sourceLore.glossaries).Count
  references = @($sourceResources.references).Count
  appliedStyle = $sourceResources.appliedStyle.name
}
Get-ChildItem -LiteralPath $migrationRoot -Filter 'source-*.json' |
  Get-FileHash -Algorithm SHA256
```

Expected: 名称为《遗产猎人》，`writingBibleMissing=True`；数量和哈希完整输出。若任一 JSON 解析失败则停止。

### Task 2: 在生产 Web UI 新建目标长篇

**Files:**
- Create: `tmp/production-long-serial-settings-migration-cmnhec5rb0000tx6g0jd0myl2/target-novel-id.txt`

- [ ] **Step 1: 加载浏览器控制 Skill 并打开生产首页**

Run: 使用 `browser:control-in-app-browser`，打开 `https://inkforge.cn`。

Expected: 页面显示用户 `nie` 的项目列表；若需要登录，等待用户在浏览器中完成，不读取密码。

- [ ] **Step 2: 创建目标项目**

在“新建小说”中填写：

```text
名称：遗产猎人（迁移）
简介：使用 source-novel.json 的 summary 原文
篇幅：长篇连载
目标总字数：1000000
题材、核心卖点、读者承诺：源作品没有 WritingBible，保持为空
```

Expected: 创建成功并进入 `/workspace/{targetNovelId}`；目标 ID 与源 ID 不同。

- [ ] **Step 3: 记录并回拉目标 ID**

从当前 URL 取得 `targetNovelId`，用 `apply_patch` 写入 `target-novel-id.txt`，随后运行：

```powershell
$targetNovelId = (Get-Content -LiteralPath (Join-Path $migrationRoot 'target-novel-id.txt') -Raw -Encoding utf8).Trim()
@{ novelId = $targetNovelId; outputFile = (Join-Path $migrationRoot 'target-initial-novel.json') } |
  ConvertTo-Json -Compress | & $operator long.novel.get
```

Expected: 返回名称《遗产猎人（迁移）》、`storyLengthProfile=long_serial`、`targetTotalWordCount=1000000`。

### Task 3: 复制单例设定

**Files:**
- Read: `source-planning.json`

- [ ] **Step 1: 保存故事背景**

在目标项目“创作资料 -> 故事背景”中粘贴 `sourcePlanning.storyBackground.content` 的完整原文并保存。

Expected: 保存成功；重新打开后首尾内容与源文本一致。

- [ ] **Step 2: 保存世界设定**

在“创作资料 -> 世界设定”中粘贴 `sourcePlanning.worldSetting.content` 的完整原文并保存。

Expected: 保存成功；重新打开后首尾内容与源文本一致。

- [ ] **Step 3: 核对作品圣经**

在“创作资料 -> 作品圣经”中确认：

```text
篇幅：长篇连载
目标总字数：1000000
其余字段：空
```

点击保存，即使当前显示值未变化，也必须形成目标项目自己的 `WritingBible`。

Expected: 保存成功，刷新后仍为长篇连载和 `1000000`。

### Task 4: 按依赖顺序复制世界观实体

**Files:**
- Read: `source-lore.json`

- [ ] **Step 1: 创建所有根地点**

对 `sourceLore.locations` 中 `parentId` 为空的记录逐条创建，完整复制 `name`、`aliases`、`type`、
`climate`、`culture`、`description`。

Expected: 根地点数量与源一致；目标地点名称唯一可定位。

- [ ] **Step 2: 分层创建子地点**

按父地点已存在的顺序处理 `parentId` 非空记录，完整复制字段，并通过源父地点名称选择对应目标父地点。

Expected: 每个子地点的父级名称与源项目一致；出现循环或找不到父级时停止。

- [ ] **Step 3: 创建势力**

逐条复制 `name`、`aliases`、`type`、`description`；`baseId` 通过源总部地点名称映射到目标地点。

Expected: 势力数量与源一致，总部地点名称一致。

- [ ] **Step 4: 创建人物**

逐条复制人物全部表单字段；`factionId` 通过源所属势力名称映射到目标势力。

Expected: 人物数量与源一致，所属势力名称一致；不填写任何源 ID。

- [ ] **Step 5: 创建人物关系**

只遍历每个人物的 `outgoingRelations`，逐条复制 `relationType`、`intimacy`、`description`、`startDate`、
`endDate`，并通过双方姓名选择目标人物。不要再次遍历 `incomingRelations` 创建重复关系。

Expected: 关系方向、双方姓名和业务字段与源一致。

- [ ] **Step 6: 创建无章节人物经历**

只复制 `experience.chapterId` 为空的记录，完整复制日期、标题、描述和影响字段；目标 `chapterId` 保持空。

Expected: 无章节经历数量与源一致；所有绑定源章节的经历明确跳过。

- [ ] **Step 7: 创建物品**

逐条复制 `name`、`aliases`、`type`、`rarity`、`effect`、`origin`、`description`；`ownerId` 通过源持有者
姓名映射到目标人物。

Expected: 物品数量与源一致，持有者姓名一致。

- [ ] **Step 8: 创建术语**

逐条复制 `term`、`definition`、`category`。

Expected: 术语数量与源一致。

### Task 5: 复制参考资料并复用文风

**Files:**
- Read: `source-resources.json`

- [ ] **Step 1: 创建参考资料**

在“创作资料 -> 参考资料”中逐条复制 `title`、`type`、`content`、`sourceUrl`。

Expected: 每次保存后列表增加一条，标题和类型正确；不复制源 `id`、`ragStatus` 或索引错误。

- [ ] **Step 2: 等待参考资料重新索引**

每条资料保存后刷新资源页并通过 `long.resources.get` 回拉；若服务只返回 pending 状态，则按条件轮询，
不使用固定长等待。

Expected: 所有目标参考资料进入成功状态；失败项停止并报告标题与错误。

- [ ] **Step 3: 应用源文风**

若 `sourceResources.appliedStyle` 非空，在目标“创作资料 -> 文风”中选择同名且同 ID 的用户级文风并应用；
若为空则保持目标未应用文风。

Expected: 目标 appliedStyle 与源一致。

### Task 6: 权威回拉与完整验收

**Files:**
- Create: `tmp/production-long-serial-settings-migration-cmnhec5rb0000tx6g0jd0myl2/target-novel.json`
- Create: `tmp/production-long-serial-settings-migration-cmnhec5rb0000tx6g0jd0myl2/target-planning.json`
- Create: `tmp/production-long-serial-settings-migration-cmnhec5rb0000tx6g0jd0myl2/target-lore.json`
- Create: `tmp/production-long-serial-settings-migration-cmnhec5rb0000tx6g0jd0myl2/target-resources.json`

- [ ] **Step 1: 完整导出目标项目**

Run:

```powershell
@{ novelId = $targetNovelId; outputFile = (Join-Path $migrationRoot 'target-novel.json') } |
  ConvertTo-Json -Compress | & $operator long.novel.get
@{ novelId = $targetNovelId; outputFile = (Join-Path $migrationRoot 'target-planning.json') } |
  ConvertTo-Json -Compress | & $operator long.planning.get
@{ novelId = $targetNovelId; outputFile = (Join-Path $migrationRoot 'target-lore.json') } |
  ConvertTo-Json -Compress | & $operator long.lore.get
@{ novelId = $targetNovelId; outputFile = (Join-Path $migrationRoot 'target-resources.json') } |
  ConvertTo-Json -Compress | & $operator long.resources.get
```

Expected: 四条命令全部 `ok=true`。

- [ ] **Step 2: 校验长篇列表与明确排除项**

Run:

```powershell
'{}' | & $operator long.novel.list
$targetPlanning = Get-Content -LiteralPath (Join-Path $migrationRoot 'target-planning.json') -Raw -Encoding utf8 | ConvertFrom-Json
if ($targetPlanning.outline.content) { throw '目标文本大纲非空' }
if (@($targetPlanning.outlineNodes).Count -ne 0) { throw '目标包含结构化大纲节点' }
if ($targetPlanning.storyProgress) { throw '目标包含源故事进展' }
```

Expected: 列表中出现目标 ID；文本大纲为空、结构化节点数量为 0、故事进展为空。

- [ ] **Step 3: 校验单例文本和实体数量**

Run:

```powershell
$targetLore = Get-Content -LiteralPath (Join-Path $migrationRoot 'target-lore.json') -Raw -Encoding utf8 | ConvertFrom-Json
$targetResources = Get-Content -LiteralPath (Join-Path $migrationRoot 'target-resources.json') -Raw -Encoding utf8 | ConvertFrom-Json
if ($sourcePlanning.storyBackground.content -cne $targetPlanning.storyBackground.content) { throw '故事背景不一致' }
if ($sourcePlanning.worldSetting.content -cne $targetPlanning.worldSetting.content) { throw '世界设定不一致' }
foreach ($name in 'characters','factions','locations','items','glossaries') {
  if (@($sourceLore.$name).Count -ne @($targetLore.$name).Count) { throw "$name 数量不一致" }
}
if (@($sourceResources.references).Count -ne @($targetResources.references).Count) { throw '参考资料数量不一致' }
```

Expected: 命令无异常退出。

- [ ] **Step 4: 逐类核对业务字段和引用名称**

按名称排序源、目标实体，逐项核对所有非 ID、非时间戳字段；引用字段用嵌套对象名称核对：

```text
Location.parentId -> 父地点名称
Faction.baseId -> 总部地点名称
Character.factionId -> 势力名称
CharacterRelation.characterId/targetId -> 双方人物姓名
Item.ownerId -> 持有者姓名
```

Expected: 所有字段一致，目标 JSON 中不出现任何源实体 ID。

- [ ] **Step 5: 最后确认源项目未变**

重新执行 Task 1 的四个导出命令到 `source-final-*.json`，比较初始和最终 SHA-256。

Expected: 四组源快照哈希全部一致；若生产系统自动更新时间导致非业务时间戳变化，则读取完整 Diff，确认
所有业务字段和实体数量完全未变后再报告，不把哈希漂移静默视为成功。

### Task 7: 交付结果

**Files:**
- Read: `target-novel-id.txt`
- Read: `source-*.json`
- Read: `target-*.json`

- [ ] **Step 1: 汇总迁移证据**

报告以下内容：

```text
源 novelId
目标 novelId
目标名称与 long_serial 状态
背景/世界设定一致性
人物、势力、地点、物品、术语、关系、无章节经历、参考资料数量
参考资料索引结果
应用文风
明确排除项为空的证据
源项目未变的证据
任何跳过项或失败项
```

Expected: 只有全部验收项通过时才声明迁移完成；部分成功必须明确列出剩余项，不删除目标项目。
