# DeepSeek strict 空对象兼容修复

状态：实现、全量 CI 与生产发布完成；真实供应商修复后请求尚待复验。发布证据见[审计](../audits/2026-10-07-provider-error-details-release.md)。

## 原因与授权

用户已授权错误日志补丁发布后重试最后一次任务，定位原因并修复、再次提交部署。用户于
2026-10-07 手动重试，第 54 章写作任务 `cmuxtoeay3d51uct1g5ft786i` 在北京时间 16:05:13
收到 HTTP 400：`An object with no properties is not allowed.`。生产已使用日志补丁 `35213d9`，
错误来自 `/beta/chat/completions` 的工具 Schema 校验，请求 ID 为
`9ea04109-4ce2-47bf-ade9-81357e686d15`。

离线检查当前 `write_chapter` 的 24 个工具，17 个工具包含共 32 个无属性对象，来源包括十个无参工具、
可选字段的省略分支和 `null` 分支。普通 JSON Schema 验证接受这些对象，原有替身测试没有模拟此
供应商限制。仅修改无参工具不能覆盖全部原因。

## 设计与边界

- 在 DeepSeek 供应商表示层使用带必填固定字符串标记的闭合对象替代无属性对象，例如
  `{"_inkforgeEmpty":"empty"}`；标记值由单值 enum 约束。
- 编码器按原类型分别把业务空对象、null 与字段缺省编码为标记对象，解码时精确恢复 `{}`、`None`
  或缺省状态；已有联合分支标签继续区分 null 与业务空对象。提供可选值仍使用原有 value 包装。
- 标记不进入工具注册契约、Core、持久快照或业务结果。历史业务参数仅在内存中按本轮 Schema 编码，
  原消息与参数不修改；真实业务同名字段仍按原业务 Schema 处理。
- 请求继续启用 Beta strict，保留字段、工具权限、原 Schema/Pydantic 完整校验及计费流程。
  不更换模型、端点或输出额度，不自动降级、不增加重试，不修改数据库、配置及正式作品内容。
- 补充非空对象的本地构造约束和全工具 Schema 回归，覆盖两个 DeepSeek Provider 的真实请求边界。
  不用本地测试冒充供应商验收；生产请求完成与草案采用分别报告。

## 影响与验收

- 修改 `providers/deepseek_strict.py` 及相关 Provider 测试；同步默认 strict 规格、Agent 指导及 AI 写作需求。
- 全注册工具和操作收窄后的章节写作 24 工具请求中，每个 object 节点均有非空 properties、全必填及
  additionalProperties=false；测试替身遇到任意空 object 时必须拒绝请求。
- 覆盖无参根、嵌套业务空对象、数组、可选缺省、显式 null、零、false、空字符串、空数组的无损往返；
  非法标记、额外键和原契约不合法输入继续拒绝，原历史不被修改。
- 运行相关 Provider/Runtime 测试、全仓 Ruff、Agent/共享契约/鉴权 Mypy、文档链接及 diff 检查。
- 提交推送后经过完整 CI 和受控生产发布，独立核对部署 SHA、镜像、结构及健康。生产验收继续通过
  作者会话或用户 Web 重试，不绕过 Core 授权计费，不自动采用候选。

依据：[DeepSeek Function Calling 官方文档](https://api-docs.deepseek.com/zh-cn/guides/tool_calls/)
及本次生产完整失败日志；无属性对象被拒绝的直接证据来自生产响应。

## 本地验证

- Provider 与 Runtime 回归共 611 项通过；新增同形业务标记回归后的 strict 专项共 43 项通过。
- 全仓 Ruff 与 Agent/共享协议/鉴权 Mypy 通过，共检查 133 个源文件；文档及 diff 检查通过。
- 两个传输适配器的测试均发送真实 24 工具集合，并由替身递归拒绝无属性对象；无参调用及章节草案
  返回值正确恢复。替身结果不代表真实供应商已经接受修复后请求。
- 本机使用已有 `.venv/bin/pytest`、`ruff` 与 `mypy`，未安装或更新依赖；正式 CI 继续使用 frozen 依赖。

## 发布验证

- 修复提交 `8423e37bd198e234b75c0aa3ef313f4df1f8c9dd` 已发布到生产；Java/Python/Web 全量 CI 通过，
  Python 共 3809 项通过、2 项跳过，Ruff 和 133 源文件 Mypy 通过。
- 三项生产镜像精确匹配同轮 CI 清单，结构指纹、编排冒烟及公网 readiness 通过；配置不变，未执行 DDL。
- 在新 Agent 容器内纯编译实际章节写作 24 工具集合，空对象 Schema 节点数为 0；没有触发模型调用。
  此验证证明部署后的工具定义已经修正，不代表作品任务已经成功或草案已经生成。
