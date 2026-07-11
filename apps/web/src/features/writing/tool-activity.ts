import { CONTROL_TOOL_NAMES } from "@/shared/contracts/agent-control";

const CONTROL_TOOL_NAME_SET = new Set<string>(CONTROL_TOOL_NAMES);

const TOOL_LABELS: Record<string, string> = {
  get_novel_info: "查询作品信息",
  list_available_data: "查询可用资料",
  list_characters_summary: "查询角色摘要",
  get_character_detail: "读取角色详情",
  get_character_list: "查询角色列表",
  list_outline_summary: "查询大纲摘要",
  get_outline_node: "读取大纲节点",
  get_plot_progress: "查询剧情进度",
  list_foreshadowings_summary: "查询伏笔摘要",
  get_foreshadowing_detail: "读取伏笔详情",
  get_recent_chapters: "查询近期章节",
  get_chapter_content: "读取章节正文",
  get_lore_context: "查询设定上下文",
  search_lore: "搜索设定库",
  get_location_detail: "读取地点详情",
  get_faction_detail: "读取势力详情",
  get_item_detail: "读取物品详情",
  get_glossary_detail: "读取术语详情",
  get_style_profile: "读取文风画像",
  get_reference_material: "读取参考资料",
  list_reference_materials: "查询参考资料",
};

export function isVisibleToolActivity(toolName: string): boolean {
  return !CONTROL_TOOL_NAME_SET.has(toolName);
}

export function getToolActivityLabel(toolName: string): string {
  return TOOL_LABELS[toolName] ?? toolName;
}

export function countVisibleToolCalls(
  entries: ReadonlyArray<{ toolName?: string; resultSummary?: string }>
): number {
  return entries.filter((entry) =>
    entry.toolName &&
    !entry.resultSummary &&
    isVisibleToolActivity(entry.toolName)
  ).length;
}

export function getToolActivitySummary(
  completionStatus: "done" | "error",
  toolCallCount: number
): string {
  const statusLabel = completionStatus === "error" ? "未完成" : "已完成";
  return toolCallCount > 0
    ? `${statusLabel} · 工具调用 ${toolCallCount} 次`
    : `${statusLabel} · 未调用工具`;
}
