export type UpdateDiffField = {
  field: string;
  label: string;
  oldValue?: string;
  newValue?: string;
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
