export type EditBaseline<T extends { id: string }> = Readonly<{
  editingId: string;
  value: T;
}>;

export function captureEditBaseline<T extends { id: string }>(
  value: T,
): EditBaseline<T> {
  return Object.freeze({
    editingId: value.id,
    value: structuredClone(value),
  });
}

export function requireEditBaseline<T extends { id: string }>(
  editingId: string,
  baseline: EditBaseline<T> | null,
): T;
export function requireEditBaseline<T extends { id: string }>(
  editingId: null,
  baseline: EditBaseline<T> | null,
): null;
export function requireEditBaseline<T extends { id: string }>(
  editingId: string | null,
  baseline: EditBaseline<T> | null,
): T | null;
export function requireEditBaseline<T extends { id: string }>(
  editingId: string | null,
  baseline: EditBaseline<T> | null,
): T | null {
  if (editingId === null) {
    return null;
  }
  if (!baseline) {
    throw new Error("编辑基线缺失，不能保存或删除");
  }
  if (baseline.editingId !== editingId) {
    throw new Error("编辑基线不匹配，不能保存或删除");
  }
  return baseline.value;
}
