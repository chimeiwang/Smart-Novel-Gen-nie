export type ToolArgumentsParseResult =
  | { success: true; args: Record<string, unknown> }
  | {
      success: false;
      error: {
        message: string;
        rawArgumentsPreview: string;
      };
    };

export function parseToolCallArguments(rawArguments: string): ToolArgumentsParseResult {
  try {
    const parsed = JSON.parse(rawArguments || "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {
        success: false,
        error: {
          message: "tool arguments must be a JSON object",
          rawArgumentsPreview: previewRawArguments(rawArguments),
        },
      };
    }
    return { success: true, args: parsed as Record<string, unknown> };
  } catch (error) {
    return {
      success: false,
      error: {
        message: error instanceof Error ? error.message : "invalid JSON",
        rawArgumentsPreview: previewRawArguments(rawArguments),
      },
    };
  }
}

function previewRawArguments(rawArguments: string): string {
  return rawArguments.length > 500 ? `${rawArguments.slice(0, 500)}...(truncated)` : rawArguments;
}
