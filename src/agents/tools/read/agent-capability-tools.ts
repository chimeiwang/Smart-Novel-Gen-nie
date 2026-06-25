/**
 * Agent 能力卡只读工具。
 *
 * @module agents/tools/read/agent-capability-tools
 * @description 让 Agent 在判断自身能力不足或需要转交时，按需读取角色能力卡。
 */

import { z } from "zod";
import { registerTool } from "../registry";
import { readOnlyPermission } from "../permissions";
import { CoreAgentIdSchema } from "@/shared/contracts/agent";
import { formatAgentCapabilityCards, formatSingleAgentCapabilityCard } from "@/shared/contracts/agent-capabilities";

registerTool(
  {
    name: "get_agent_capability_cards",
    description:
      "按需读取 Agent 角色能力卡。" +
      "当你不确定自己是否能完成当前任务，或需要决定是否 route_to_agent 给其他 Agent 时，先调用此工具。" +
      "不需要转交时不要调用，避免无谓占用上下文。",
    inputSchema: z.object({
      agentId: CoreAgentIdSchema.optional().describe("可选。只读取某个 Agent 的能力卡；省略则返回全部 Agent 能力卡。"),
    }),
    permission: readOnlyPermission("agent.card.read"),
    toolKind: "read",
  },
  async (args) => {
    const agentId = args.agentId as z.infer<typeof CoreAgentIdSchema> | undefined;
    return agentId ? formatSingleAgentCapabilityCard(agentId) : formatAgentCapabilityCards();
  }
);
