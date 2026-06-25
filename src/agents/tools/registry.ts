/**
 * 工具注册表
 *
 * @module agents/tools/registry
 * @description Phase 3 工具层重构：统一管理所有工具的注册、查询和权限。
 *  替代 tools.ts 中的 getXxxTools() 函数和部分 createToolExecutor 逻辑。
 *
 * @phase Phase 3 — 工具层重构
 */

import { z } from "zod";
import type { ToolPermission } from "./permissions";
import { readOnlyPermission } from "./permissions";

// ============================================
// 工具注册表类型
// ============================================

/** 工具定义（兼容原 Tool 接口 + Zod schema） */
export interface ToolDefinition {
  /** 工具名称（唯一标识） */
  name: string;
  /** 工具描述（给 LLM 看的） */
  description: string;
  /** Zod 入参校验 schema */
  inputSchema: z.ZodType<Record<string, unknown>>;
  /** 权限元信息 */
  permission: ToolPermission;
  /**
   * 工具类型
   * - "read": 只读工具，始终允许
   * - "proposal": 生成修改草案，返回模板但不写库
   * - "control": Agent 控制面工具（路由、评分、更新提案等），不承载长篇内容
   * - "mutating": 直接写库，一律拦截
   */
  toolKind: "read" | "proposal" | "control" | "mutating";
}

/** 工具执行器函数 */
export type ToolExecutorFn = (
  args: Record<string, unknown>,
  state: {
    novelData: Record<string, unknown>;
    novelId?: string;
    chapterId?: string;
    taskId?: string;
    activeArtifactId?: string | null;
  }
) => string | Promise<string>;

// ============================================
// 注册表
// ============================================

const toolMap = new Map<string, ToolDefinition>();
const toolExecutorMap = new Map<string, ToolExecutorFn>();

/**
 * 注册工具到注册表
 */
export function registerTool(
  definition: ToolDefinition,
  executor: ToolExecutorFn
): void {
  if (toolMap.has(definition.name)) {
    throw new Error(`工具 "${definition.name}" 已注册，请检查是否重复`);
  }
  toolMap.set(definition.name, definition);
  toolExecutorMap.set(definition.name, executor);
}

/**
 * 获取工具定义
 */
export function getTool(name: string): ToolDefinition | undefined {
  return toolMap.get(name);
}

/**
 * 获取所有工具定义
 */
export function getAllTools(): ToolDefinition[] {
  return Array.from(toolMap.values());
}

/**
 * 按能力域列表获取工具（Phase 3：Agent 通过 capability 获取工具）
 */
export function getToolsByCapabilities(capabilities: string[]): ToolDefinition[] {
  const set = new Set(capabilities);
  return Array.from(toolMap.values()).filter(
    (t) => set.has(t.permission.capability) && t.toolKind !== "mutating"
  );
}

export function getToolsByCapability(capability: string): ToolDefinition[] {
  return Array.from(toolMap.values()).filter(
    (t) => t.permission.capability === capability && t.toolKind !== "mutating"
  );
}

/**
 * 按 Agent ID 获取工具
 */
export function getToolsByAgent(agentId: string): ToolDefinition[] {
  return Array.from(toolMap.values()).filter(
    (t) =>
      t.toolKind !== "mutating" &&
      (!t.permission.agentIds || t.permission.agentIds.includes(agentId))
  );
}

/**
 * 执行工具
 */
export async function executeTool(
  name: string,
  args: Record<string, unknown>,
  state: {
    novelData: Record<string, unknown>;
    novelId?: string;
    chapterId?: string;
    taskId?: string;
    activeArtifactId?: string | null;
  }
): Promise<string> {
  const def = toolMap.get(name);
  if (!def) {
    return `未知工具: ${name}`;
  }

  // P1 修复：只拦截 mutating 工具，proposal 工具可正常执行返回模板
  if (def.toolKind === "mutating") {
    return JSON.stringify({
      error: "WRITE_TOOL_DISABLED",
      message: `直接写入工具 "${name}" 已禁用。请使用 propose_* 工具生成修改草案，用户确认后由服务端事务执行。`,
      suggestion: {
        type: "updates",
        toolName: name,
        action: "请调用对应的 propose_* 工具替代此工具。",
      },
    });
  }

  // Phase 0：control 工具由 runtime 拦截处理，此处返回简单确认
  if (def.toolKind === "control") {
    return JSON.stringify({ acknowledged: true, tool: name });
  }

  // Zod 入参校验
  try {
    def.inputSchema.parse(args);
  } catch (error) {
    const zodError = error as { errors?: Array<{ message: string }> };
    const messages = zodError.errors?.map((e) => e.message).join("; ") || "参数校验失败";
    return `参数错误: ${messages}`;
  }

  // 执行
  const executor = toolExecutorMap.get(name);
  if (!executor) {
    return `工具 "${name}" 未注册执行器`;
  }

  return executor(args, state);
}

/**
 * 将注册表中的工具转换为 OpenAI 函数调用格式
 * 兼容原 tools.ts 的 getToolsForOpenAI()
 */
export function getOpenAITools(names?: string[]): Array<{
  type: "function";
  function: { name: string; description: string; parameters: Record<string, unknown> };
}> {
  const tools = names
    ? Array.from(new Set(names)).map((n) => toolMap.get(n)).filter(Boolean) as ToolDefinition[]
    : Array.from(toolMap.values()).filter((t) => t.toolKind !== "mutating");

  return tools.map((tool) => ({
    type: "function" as const,
    function: {
      name: tool.name,
      description: tool.description,
      parameters: zodToJsonSchema(tool.inputSchema),
    },
  }));
}

/**
 * 将 Zod schema 转换为 JSON Schema（OpenAI 兼容格式）
 * Zod v4 原生支持 toJSONSchema()，剔除 OpenAI 不兼容的字段。
 */
function zodToJsonSchema(schema: z.ZodType<unknown>): Record<string, unknown> {
  const jsonSchema = schema.toJSONSchema() as Record<string, unknown>;
  // 剔除 OpenAI 不支持的字段
  const { $schema, ...rest } = jsonSchema;
  return stripNeverProperties(rest as Record<string, unknown>);
}

function stripNeverProperties(schema: Record<string, unknown>): Record<string, unknown> {
  const cloned = { ...schema };
  const properties = cloned.properties;
  if (properties && typeof properties === "object" && !Array.isArray(properties)) {
    const nextProperties: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(properties as Record<string, unknown>)) {
      if (isNeverJsonSchema(value)) continue;
      nextProperties[key] = isJsonSchemaObject(value) ? stripNeverProperties(value) : value;
    }
    cloned.properties = nextProperties;
  }

  for (const key of ["items", "additionalProperties", "not", "anyOf", "oneOf", "allOf"] as const) {
    const value = cloned[key];
    if (Array.isArray(value)) {
      cloned[key] = value.map((item) => isJsonSchemaObject(item) ? stripNeverProperties(item) : item);
    } else if (isJsonSchemaObject(value)) {
      cloned[key] = stripNeverProperties(value);
    }
  }

  return cloned;
}

function isJsonSchemaObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isNeverJsonSchema(value: unknown): boolean {
  return isJsonSchemaObject(value) &&
    Object.keys(value).length === 1 &&
    isJsonSchemaObject(value.not) &&
    Object.keys(value.not).length === 0;
}

/**
 * 获取所有只读工具名称列表（用于 WRITE_TOOL_NAMES 兼容）
 */
export function getWriteToolNames(): string[] {
  return Array.from(toolMap.values())
    .filter((t) => t.toolKind === "mutating")
    .map((t) => t.name);
}
