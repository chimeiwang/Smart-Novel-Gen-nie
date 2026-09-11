# Seedance 2.5 官方接口契约核对

日期：2026-09-10

状态：已完成只读文档核对；没有登录控制台、没有创建任务、没有传输素材，也没有发生供应商费用。

权威来源：

- [创建视频生成任务](https://docs.volcengine.com/docs/82379/1520757?lang=zh)，页面最近更新时间为 2026-09-09；
- [查询视频生成任务](https://docs.volcengine.com/docs/82379/1521309?lang=zh)，页面最近更新时间为 2026-09-09；
- [取消或删除视频生成任务](https://docs.volcengine.com/docs/82379/1521720?lang=zh)。

本文只记录本次实现实际依赖的供应商事实。费用、模型开通条件和可用区域在真实试制前必须再次从官方控制台核对，不能用本文替代上线时的实时配置。

## 创建与查询边界

- 创建任务为 `POST /api/v3/contents/generations/tasks`，返回供应商任务 ID；生成是异步过程，Core 必须短提交、耐久查询，不能在浏览器请求内等待完成。
- 官方示例使用模型 ID `doubao-seedance-2-5-260628`。模型 ID 是每次生成清单中的冻结事实，环境默认值变化不能改写旧任务。
- `omni_reference_task_type` 可为 `auto`、`reference`、`edit` 或 `extend`。当前逐镜新素材采用显式 `reference`，以便在创建时得到更早的参数校验；不能依赖 `auto` 后在异步阶段才发现类型不匹配。
- `reference` 支持图片、视频、音频与文本的组合。Seedance 2.5 上限为图片 30 张、视频 10 个、音频 10 段；所有参考视频合计不超过 30 秒，所有参考音频合计不超过 30 秒。
- 图片 role 为 `reference_image`，视频 role 为 `reference_video`，音频 role 为 `reference_audio`。适配器必须按模态生成对应的 `image_url`、`video_url`、`audio_url` 内容块，不能把所有素材强转成图片。

## 输出参数

| 参数 | Seedance 2.5 官方约束 | 本产品处理 |
| --- | --- | --- |
| `duration` | `4..30` 秒，或 `-1` 由模型选择；视频编辑只允许 `-1` | 供应商中立契约保留完整范围；逐镜产品策略可以选更小子集，但须冻结原值 |
| `resolution` | `480p`、`720p`、`1080p`，默认 `720p` | 用枚举校验；不能向 2.5 发送 `4k` |
| `ratio` | `16:9`、`4:3`、`1:1`、`3:4`、`9:16`、`21:9`、`adaptive` | 每个任务冻结；参考生视频可显式指定，编辑／延长使用 `adaptive` |
| `generate_audio` | 默认 `true`；有声结果为单声道 | 明确冻结，不以字段缺失猜测作者意图 |
| `output_format` | `mp4` 或 `mov`，默认 `mp4` | 当前网页预览优先 `mp4`；专业后期请求可明确选择 `mov` |
| `watermark` | 默认 `false` | 每个任务冻结 |

官方建议中文提示词不超过 500 字、英文不超过 1000 词。这是质量建议，不作为静默截断规则；产品应在编译提示词时给出可见提示，并完整保留作者原始制作意图。

## 状态、归档与恢复

- 查询状态包含 `queued`、`running`、`succeeded`、`failed` 和 `cancelled`；超过 `execution_expires_after` 的任务会标记为 `expired`。
- 官方只保证 `queued` 任务可以取消。产品不能把“已请求取消”直接显示成取消成功，必须继续回读权威任务状态。
- `video_url` 与可选 `last_frame_url` 有效期均为 24 小时；Seedance 2.5 结果 URL 的下载次数上限为 100 次。Core 在成功后应尽快归档到受控存储，并把本地素材哈希、时长和来源清单写入不可变 Take。
- 创建请求遇到超时或网络中断时，结果可能未知。普通重试不得自动换新业务任务再次 POST；必须保存同一内部任务身份，进入人工／对账恢复，避免重复付费。
- 查询返回的 `usage.completion_tokens`／`usage.total_tokens` 是供应商计费对账证据。模拟模式不得伪造这组真实用量。

## 当前实施口径

供应商中立边界可以表达 Seedance 2.5 的图片、视频和音频参考，但首批逐镜 Core 流程仍可只开放经过归属、权利和公网传输检查的图片参考子集。能力身份必须明确写出这个子集，不能把“适配器可表达”宣传为“产品已经开放全模态”。

本轮 `SEEDANCE_EXECUTION_MODE` 保持 `simulated`，模拟结果必须标记 `simulated_placeholder`。真实 POST／GET 函数继续独立存在但不会被调用；本审计不能证明真实画质、声音、供应商计费或生产容量。
