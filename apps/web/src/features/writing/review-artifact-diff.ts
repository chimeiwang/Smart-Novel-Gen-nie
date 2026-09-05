export type UpdateDiffField = {
  field: string;
  label: string;
  oldValue?: string | null;
  newValue?: string | null;
};

export type UpdateDiffItem = {
  section: string;
  action: string;
  name: string;
  fields: UpdateDiffField[];
};

export type SelectionDiff = {
  type: "selection";
  mode?: string;
  resourceType?: string;
  resourceId?: string;
  selectionStart?: number;
  selectionEnd?: number;
  selectedText?: string;
  replacement: string;
  before: string;
  after: string;
  candidate?: string;
  prefix?: string;
  suffix?: string;
};

export type UpdateDiffValueDescription = {
  text: string;
  isPlaceholder: boolean;
};

export function describeUpdateDiffValue(
  value: string | null | undefined,
  missingText: string,
): UpdateDiffValueDescription {
  if (value === null) {
    return { text: "未设置（null）", isPlaceholder: true };
  }
  if (value === undefined) {
    return { text: missingText, isPlaceholder: true };
  }
  if (value.length === 0) {
    return { text: "空字符串", isPlaceholder: true };
  }
  if (value.trim().length === 0) {
    return {
      text: `仅空白文本：${JSON.stringify(value)}`,
      isPlaceholder: true,
    };
  }
  return { text: value, isPlaceholder: false };
}

export function isSelectionDiff(value: unknown): value is SelectionDiff {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Record<string, unknown>;
  return candidate.type === "selection"
    && typeof candidate.before === "string"
    && typeof candidate.after === "string"
    && typeof candidate.replacement === "string";
}

export function normalizeReviewArtifactDiff(
  diff: unknown,
  fallback: unknown,
): { selectionDiff: SelectionDiff | null; updateDiff: UpdateDiffItem[] } {
  if (isSelectionDiff(diff)) {
    return { selectionDiff: diff, updateDiff: [] };
  }
  if (Array.isArray(diff)) {
    return { selectionDiff: null, updateDiff: diff as UpdateDiffItem[] };
  }
  return {
    selectionDiff: null,
    updateDiff: Array.isArray(fallback) ? fallback as UpdateDiffItem[] : [],
  };
}
