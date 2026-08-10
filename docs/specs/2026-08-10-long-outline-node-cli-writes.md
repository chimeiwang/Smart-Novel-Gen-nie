# 长篇分层大纲节点生产写入规格

## 状态

- 日期：2026-08-10
- 状态：实施中
- 范围：公共 Core API、Web、`inkforge-cli` 与生产小说操作 Skill

## 背景

InkForge 已有“阶段/卷 → 剧情单元 → 章节组”的 `OutlineNode` 数据模型和公共读接口，但生产 CLI 与
操作 Skill 只能读取节点。现有公共节点写接口也缺少创建幂等身份以及更新、删除的版本前置条件，不能
直接作为无状态生产操作入口。

## 目标

1. 新增 `long.outline-node.create`、`long.outline-node.update`、`long.outline-node.delete`。
2. 创建使用稳定 `clientRequestId`，相同请求重放不重复创建，不同内容重放返回 409。
3. 更新和删除使用 `expectedUpdatedAt`；过期版本返回 `OUTLINE_NODE_VERSION_CONFLICT`。
4. 相同内容更新不推进版本；删除继续拒绝仍有子节点的节点。
5. Web 调用方同步携带幂等键和编辑基线版本。
6. 生产 Skill 执行写前完整节点树回读、单次 Diff 确认、一次写入和写后回读。
7. 不修改 PostgreSQL schema，不开放伏笔写入或整树危险替换命令。

## 公共契约

- `POST /api/v1/novels/{novelId}/outline-nodes`
  - 请求：节点完整创建字段加 `clientRequestId`。
  - 响应：节点完整字段加 `effective`。
- `PATCH /api/v1/novels/{novelId}/outline-nodes/{nodeId}`
  - 请求：至少一个节点字段加非空 `expectedUpdatedAt`。
  - 响应：节点完整字段加 `effective`。
- `DELETE /api/v1/novels/{novelId}/outline-nodes/{nodeId}`
  - 请求：非空 `expectedUpdatedAt`。
  - 响应：`deletedId` 与 `effective=true`。

创建 ID 复用现有 `command_resource_id()`，命名空间固定为 `outline_nodes`。更新和删除在小说级锁内读取
并锁定目标节点，先校验版本，再验证层级或子节点约束。所有错误继续完整透传公共业务码和详情。

## CLI 输入

- create：`novelId + clientRequestId + data`
- update：`novelId + outlineNodeId + expectedUpdatedAt + data`
- delete：`novelId + outlineNodeId + expectedUpdatedAt`

`data` 只允许节点业务字段；创建要求非空 `title` 和合法 `kind`，更新要求至少一个业务字段。三个命令
均为 JSON 输入、JSON 输出、需要身份；只有 create 声明 `requiresClientRequestId=true`。

## 验收

1. Core 覆盖创建重放、创建冲突、相同更新、有效更新、过期更新、过期删除和有子节点删除拒绝。
2. CLI 覆盖精确 method/path/body、字段校验、ID 编码和 registry 元数据。
3. Web 生成客户端无漂移，节点创建、更新、删除分别携带稳定请求 ID 或编辑基线版本。
4. 生产 Skill 精确开放三条命令，命令计数与配置仓库 registry 一致，离线测试和 Skill 校验通过。
5. 数据库 schema 指纹不变。
