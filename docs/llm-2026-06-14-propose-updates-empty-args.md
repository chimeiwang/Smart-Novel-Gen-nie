# 2026-06-14 propose_updates 空参数问题记录

## 背景

用户请求网文编辑评审大纲，并要求编辑把修改任务交给其他 Agent，待其他 Agent 修改后再由编辑复审，最后再交给用户审核。

06-14 最后一轮日志中，编辑成功完成评审并通过 `route_to_agent` 转交给剧情顾问。剧情顾问随后尝试调用 `propose_updates` 提交大纲修改草案，但工具参数校验失败。

## 现象

日志位置：`logs/llm/llm-2026-06-14.log`

相关请求：

- `REQUEST #1781449007229-1vehq7`
- `REQUEST #1781449026191-m2kedw`

两条剧情链路均出现相同问题：

```text
Tool: propose_updates
Arguments: {}
Result: control tool "propose_updates" 参数校验失败

Zod issues:
- summary: Invalid input: expected string, received undefined
- updates: Invalid input: expected object, received undefined
```

第二次空参调用后，runtime 按设计停止本轮工具循环，并返回“未保存任何变更”。

## 直接原因

模型调用 `propose_updates` 时实际发出的 tool arguments 是空对象 `{}`。

但 `propose_updates` 的 contract 要求至少包含：

```ts
type ProposeUpdatesArgs = {
  summary: string;
  updates: {
    outline?: OutlineStatusUpdate[];
    outlineAdjustments?: OutlineAdjustment[];
    foreshadowing?: ForeshadowingUpdate[];
    // 其他 section 省略
  };
};
```

因此后端 Zod 校验拒绝该调用是正确行为，不是数据库写入失败，也不是工具执行异常。

## 相关代码

- `src/shared/contracts/agent-control.ts`：`ProposalUpdatesToolArgsSchema`
- `src/agents/runtime/agent-runtime.ts`：control tool 参数解析、失败计数、连续失败后停止工具循环
- `src/agents/tools/control/control-tools.ts`：`propose_updates` 工具描述
- `src/agents/graph/nodes/plot-advisor-node.ts`：剧情顾问关于 `propose_updates` 的提示词

## 根因判断

提示词告诉剧情顾问“需要修改大纲时调用 `propose_updates`”，也说明了 `updates` 内部结构，但可复制的完整调用样例不够明确，尤其缺少 `summary`、`artifactKey`、`reviewerAgent`、`submitForReview` 与 `updates` 的完整组合示例。

在“先让编辑复审，再交给用户审核”的任务中，剧情顾问还应使用稳定 `artifactKey`，并设置 `reviewerAgent: "编辑"` 或随后路由给编辑。该流程语义已经存在，但模型没有稳定转化为合法 tool arguments。

## 本次处理状态

本次只记录问题，不修复 `propose_updates` 提示词或工具协议。

后续建议单独处理：

1. 在剧情顾问提示词中加入完整 `propose_updates` tool call 示例，包含 `summary` 和 `updates`。
2. 对“需要编辑复审后再给用户审核”的场景，示例应包含 `artifactKey`、`reviewerAgent: "编辑"`、`submitForReview: true`。
3. 增加回归测试，覆盖剧情顾问提交大纲草案时不能空参调用 `propose_updates`。
