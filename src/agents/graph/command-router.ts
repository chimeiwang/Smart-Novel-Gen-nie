import { Command, END } from "@langchain/langgraph";
import type { CoreAgentId } from "./state";

export type GraphRoute =
  | "loreAdvisor"
  | "plotAdvisor"
  | "author"
  | "validator"
  | "editor"
  | "statusReport"
  | "end";

const AGENT_NODE_MAP: Record<CoreAgentId, GraphRoute> = {
  "设定": "loreAdvisor",
  "剧情": "plotAdvisor",
  "写作": "author",
  "校验": "validator",
  "编辑": "editor",
};

export function mapAgentToNode(agentId: CoreAgentId | null | undefined): GraphRoute {
  if (!agentId) return "end";
  return AGENT_NODE_MAP[agentId] ?? "end";
}

export function toGraphRoute(result: { nextAgent?: CoreAgentId | null }): GraphRoute {
  return mapAgentToNode(result.nextAgent);
}

export type ProcessResultCommandUpdate = {
  nextAgent?: CoreAgentId | null;
  controlEvents?: undefined;
};

export function toGraphCommand<TUpdate extends object & ProcessResultCommandUpdate>(result: TUpdate): Command {
  const { nextAgent: _nextAgent, ...rest } = result;
  const route = toGraphRoute(result);
  return new Command({
    update: {
      ...rest,
      nextAgent: null,
      controlEvents: undefined,
    },
    goto: route === "end" ? END : route,
  });
}
