# Episode 视频本机隔离验收

该入口验证新的独立分集生产链。它只使用随机命名的本机 PostgreSQL、普通 Redis、执行 Redis 和临时目录，
不会读取仓库 `.env`，不会连接服务器开发库或正式库。Seedance 固定为 `simulated`，密钥为空且供应商开关关闭。

完整执行：

```bash
.venv/bin/python tests/video_local_e2e/run_local.py all
```

默认把脱敏 JSON 回执和 A／B／C 三张浏览器截图写入 `output/video-local-e2e/<UTC 时间>/`，无论通过或失败都
终止本机 Core／Agent／Web 进程并删除本轮容器和卷。调试时可以分步运行：

```bash
.venv/bin/python tests/video_local_e2e/run_local.py build
.venv/bin/python tests/video_local_e2e/run_local.py prepare
.venv/bin/python tests/video_local_e2e/run_local.py start <prepare 返回的 directory>
.venv/bin/python tests/video_local_e2e/run_local.py wait <directory>
.venv/bin/python tests/video_local_e2e/run_local.py scenario <directory>
.venv/bin/python tests/video_local_e2e/run_local.py cleanup <directory>
```

`scenario --no-browser` 只用于定位 API／媒体问题，不能作为完整验收。`--keep` 只保留临时日志和环境文件以便
本机排错，仍会清理随机容器和卷；这些文件可能含一次性本机凭据，不应提交或复制到审计文档。

固定业务场景：

1. 《雨夜交信》跨第 12、13 章取材，确认剧本与两镜分镜，冻结定妆和关键帧，创建 B0；两镜模拟生成各形成
   一个不可变 Take，经人工 Adoption 创建 B1，再以独立 clipId 完成重复、裁切、原声保留／静音、字幕和交付。
2. 《拆信》与第一集共享第 13 章来源，明确引用第一集正式剧本的 `letter_handoff` 状态；三日前回忆使用独立
   剧情时间，不绑定该承接。
3. 第一集 v2 将“交信”改为“收回信”，第二集只生成开信场的直接影响项；三日前回忆保持不变，第一集 v1 的
   B1、粗剪、混音和交付仍按精确身份可读。

浏览器断言必须和同轮公共 API 及 PostgreSQL 计数一起通过。截图只能证明界面结果可见，不能单独证明持久化、
真实 Seedance 画质、供应商计费或生产开放。
