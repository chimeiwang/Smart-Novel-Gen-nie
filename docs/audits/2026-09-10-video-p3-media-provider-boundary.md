# 剧集制作 P3 媒体与供应商边界审计

日期：2026-09-10

状态：P3 实施前收敛完成，Agent 供应商中立边界与默认模拟已实现并通过测试；Episode 制作基线下的
Render、Take、粗剪、声音和导出尚未完成组合接线，不能据此宣称 P3 交付。

范围：P3-2 的供应商短调用与模拟边界，以及 P3-3／P3-4 旧实现的代码级复用和退役清单。本次没有修改
数据库、Java、CLI 或前端，没有运行 Maven，没有连接 Seedance 或其他外部视频供应商。

依据：[剧集制作实施规格](../specs/2026-09-10-video-episode-production-implementation.md)、
[分批实施计划](../plans/2026-09-10-video-episode-production-rebuild.md)、
[Seedance 2.5 接入设计](../specs/2026-09-09-seedance-25-lore-visual-production.md)和
[本轮官方契约核对](2026-09-10-seedance-25-contract-check.md)。供应商参数以 2026-09-10 读取的国内官方文档
为依据；账号模型清单、配额、真实输出和计费仍未验证。

## 1. 当前调用链与完成改动

当前兼容链为：

```text
Core 冻结 Render Task
  -> Core Reconciler 短提交／短查询
  -> Agent Seedance 内部 HTTP 兼容路由
  -> VideoGenerationRequest / Submission / Result
  -> Seedance Provider wire 适配或本地模拟结果
  -> Core 归档／FFmpeg 模拟器
  -> ffprobe 验证
  -> 受控 VideoAsset 与不可变 Take
```

新增 `providers/video_generation.py`，定义供应商中立的请求、参考素材、受理结果、查询结果、媒体来源、失败和
Provider 协议。它只携带冻结输入，不读取 Core、不重编译提示词、不持久化短时 URL。中立 reference DTO 已表达
图片／视频／音频模态、来源时长、4～30 秒或 `-1`、480p／720p／1080p、官方画幅及 MP4／MOV；Seedance adapter
再执行图片 30、视频 10、音频 10，以及视频／音频各自总时长 30 秒的 Provider 能力门禁。成功结果必须与状态
闭合；进行中状态不能提前携带媒体；失败终态必须携带错误。

`seedance_router.py` 继续保留现有 Java 调用所需的 `SeedanceRender*` HTTP wire 契约，但在路由边界转换为中立
对象。当前兼容路由显式选择 `image_reference_v1`：只接受既有契约的 1～20 张图片、4～12 秒、720p MP4，
不把 Provider 的完整多模态能力冒充成已开放产品范围。`SeedanceProvider` 不再让当前逐镜短调用直接依赖该
wire DTO，只负责中立对象和方舟字段之间的翻译；其身份同时区分完整 reference capability 和默认图片子集。
后续替换 Provider 时可以实现同一协议，不需要改变 Core 的制作任务语义。

默认模拟提交确定性返回与 taskId 绑定的 providerTaskId；查询明确返回
`media_kind=simulated_placeholder` 和 `inkforge-simulated://` 标识。兼容 HTTP 响应仍由 Core 的冻结
`executionMode`、精确任务标识和模拟 URL 三者共同校验，随后才进入 FFmpeg 本地占位视频分支。模拟路径不创建
HTTP 客户端，不需要密钥，也不伪造供应商 usage。

Seedance wire 编译按模态生成 `reference_image`、`reference_video` 或 `reference_audio`，并传递明确的
`omni_reference_task_type=reference` 与 output format。查询结果保留 usage、媒体来源和可选 last-frame URL；
当前 Java 兼容响应尚不消费 last-frame，P3 若使用它必须先纳入正式跨服务契约，不能从临时 URL 事后推断。

真实付费创建仍唯一收口在 `_create_live_task()`，真实查询唯一收口在 `_query_live_task()`。只有 Agent 配置为
`live`、开关启用且存在密钥时才可进入；创建超时、5xx、无效 JSON 或缺少任务 ID 一律归为提交未知，不能当作
明确失败自动重提。查询只访问既有 providerTaskId，且将该 ID 编码为一个 URL path segment，避免供应商返回值
改变查询路径。官方查询结果中的视频和末帧 URL 只有 24 小时有效且下载次数受限；现有 Core 成功分支立即取得
归档租约、下载、探测并保存受控文件，供应商 URL 不写成播放事实。归档失败继续查询同一 providerTaskId，
不得再次创建任务。

## 2. 可以复用的旧实现

| 现有实现 | P3 复用判断 | 必须保持的约束 |
| --- | --- | --- |
| `VideoRenderReconciler` 的领取、租约、短提交／查询、归档恢复状态机 | 复用算法 | 提交未知禁止自动重提；归档失败只查询同一 providerTaskId；并发完成只产生一个逻辑 Take |
| `VideoRenderManifestCodec` 的规范 JSON 与哈希复核 | 重绑定后复用 | P2 必须先把来源改为 episode／baseline／shotVersion，历史清单只读 |
| `ProviderAssetTokenCodec` 与受控素材读取 | 复用 | 短时令牌只用于确切 assetId 与 sha256；模拟不需要公网 URL |
| `SeedanceResultUrlPolicy`、限流下载和 `VideoAssetStore.saveStream` | 抽成通用归档能力后复用 | 禁止重定向；限制主机、字节数和超时；临时供应商 URL 不作为播放事实 |
| `FfprobeVideoMediaProbe` | 直接复用 | 必须有有效视频流、画面尺寸、帧数和有限正时长，失败文件不得登记为 Take |
| `FfmpegVideoRenderSimulator` | 重绑定清单后复用 | 画面必须显示“模拟视频 · 未调用真实模型”；执行方式不匹配时拒绝 |
| `FfmpegVideoPostProductionMediaProcessor` | 复用媒体执行与安全边界 | 无 shell、参数数组、超时、哈希复核、受控临时目录和完成后存储 |
| `VideoEpisodeFfmpegPlan` 的比例、裁切、字幕与滤镜图生成 | 复用纯计算部分 | 输入清单改为新 clip／adoption／声音决定后重新验收，旧身份字段不能继续作为权威 |
| 后期命令的 advisory lock、canonical hash 和稳定 clientRequestId | 复用 | 领域结果与命令回执同事务；未知响应先回读，不更换请求 ID 重写 |

## 3. 必须替换或退出的旧业务语义

1. `VideoRenderService`、`VideoRenderRepository` 和公开控制器仍以 `adaptationId + shotId` 创建和确认 Take；
   新链必须使用 `episodeId + productionBaselineId + shotVersionId`，生成成功只登记候选，作者采用通过
   `VideoTakeAdoption` 和新基线生效。
2. 旧 `VideoShotTakeHead` 把“当前 Take”直接挂到镜头。它不能承担新版采用事实；历史读取可保留，新写入在
   Adoption／Baseline 接通后关闭。
3. `VideoEpisodeExportManifest/1.0` 仍冻结 `adaptationId + episodePlanVersionId + episodeNo`，片段只有
   `shotId + takeId`。新版必须冻结稳定 `episodeId`、制作基线、编辑版本、声音版本、独立 `clipId`、
   `adoptionId` 和真实媒体区间。
4. `JooqVideoTimelineRepository` 仍以正式镜头集合为完整性基准，并要求 Take 直接属于同一 Shot；这与“允许
   明确省略镜头、重复同一素材区间、通过 Adoption 使用素材”冲突，不能只替换列名。
5. 后期 Repository／Service／workspace 仍以 adaptationId 和 episodeNo 寻址，Keyframe 仍直接绑定旧 Shot。
   P3 必须在 P2 稳定 ShotVersion 和基线结构完成后整体改接，不能同时保留两套可新建后期流程。
6. `SeedanceResultArchiver` 的下载策略可复用，但类型名和错误码仍绑定供应商；新 Core 媒体归档端口应表达通用
   Provider 媒体，Seedance 只在 URL policy 或 adapter 配置中出现。
7. 现有 Core `VideoRenderGateway` 与生成 Java 模型仍带 Seedance 名称。本批为避免在 P2 结构尚未稳定时扩大
   跨服务契约，保留为兼容传输壳；P3 组合接线时应统一改成 provider-neutral 名称或明确记录其历史兼容期限。
8. `SeedanceProvider.submit(SeedancePromptPackage)` 与 `query()` 当前没有业务调用方，属于旧 Scene 制作包残留；
   新链不得重新接入。P4 在核对历史执行无需它们后删除，不能把这组无调用方法当作第二套 Provider 入口。

## 4. P2 完成后的 P3 接线顺序

1. 从已确认 ProductionBaseline 读取确切 shotVersion、PromptVersion、视觉参考、Keyframe、声音意图和
   executionMode，生成新版不可变 Render Manifest；禁止拼装各对象当前 head。
2. 创建任务和命令回执同事务；Reconciler 沿用现有状态机。模拟查询只返回占位来源事实，真正 MP4 仍由 Core
   在受控存储内生成并探测。
3. 归档完成只创建原始 Take；作者对照目标 shotVersion 后创建 Adoption，再确认新的 ProductionBaseline。
   原任务、原 Take、原基线都保持不可变。
4. 新粗剪版本保存独立 clipId、adoptionId、sourceInMs／sourceOutMs、输出时长与省略决定；同一 Adoption
   可以形成多个 clip，不能把 shotId 当时间线片段身份。
5. 声音版本对每个视频 clip 明确 `keep_original` 或 `mute_original`，再叠加对白、音乐或环境声素材；字幕锚定
   稳定台词和实际时间区间。没有显式决定时拒绝导出。
6. 导出任务一次性冻结 productionBaseline、editVersion、mixVersion、字幕和全部素材哈希。完成文件经 ffprobe
   验证后创建不可变交付版本；旧基线可以用它自己的确切组合再次导出。

## 5. 验证证据与剩余限制

- Agent Service 全量测试：1792 项通过；供应商边界定向 53 项通过。
- 新中立边界、Seedance adapter 与 router 的 Ruff 通过；三个源文件的严格 Mypy 通过。
- 模拟测试把网络客户端替换为“调用即失败”的桩，提交、重放和跨 Provider 实例查询仍成功；因此本轮没有
  Seedance 网络请求。
- 真实 POST／GET 只使用 `httpx.MockTransport` 验证字段翻译、状态规范化、错误分类和一次提交，没有真实密钥、
  费用或输出画质证据。
- 本批没有运行 Maven；Java Render／Take／后期仍等待 P2 新归属稳定后由主任务串行编译和集成验收。
- 没有数据库迁移、服务器开发库操作、生产开关修改或生产发布。

P3 只有在新 Episode 基线下完成模拟 MP4、Take Adoption、粗剪、声音、导出和公共 API 回读的组合验收后，
才可以从“实施前收敛”更新为完成。
