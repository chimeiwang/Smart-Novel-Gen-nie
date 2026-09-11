import { useEffect, useId } from "react";

type EditorScope = "visual" | "text" | "references";
type VisualEditorState = { novelId: string; dirty: boolean; busy: boolean; scope?: EditorScope };
const editors = new Map<string, VisualEditorState>();

export function registerVisualEditor(id: string, state: VisualEditorState): () => void {
  editors.set(id, state);
  return () => { editors.delete(id); };
}

export function visualEditorLeaveState(novelId: string, scope?: EditorScope): "busy" | "dirty" | "clear" {
  const matching = [...editors.values()].filter((editor) => editor.novelId === novelId && (!scope || (editor.scope ?? "visual") === scope));
  if (matching.some((editor) => editor.busy)) return "busy";
  return matching.some((editor) => editor.dirty) ? "dirty" : "clear";
}

/** 在会卸载视觉编辑器的工作区导航前调用；页签内保留组件时无需调用。 */
export function confirmVisualEditorLeave(novelId: string, scope?: EditorScope): boolean {
  const state = visualEditorLeaveState(novelId, scope);
  if (state === "busy") {
    window.alert("设定或镜头参考正在保存，请等待操作完成后再离开。");
    return false;
  }
  return state === "clear" || window.confirm("还有未提交的设定或镜头参考修改，离开后将丢失。已保存的候选和正式版本会保留。确定离开？");
}

export function useVisualEditorLeaveGuard(novelId: string, dirty: boolean, busy: boolean, scope: EditorScope = "visual"): void {
  const id = useId();
  useEffect(() => registerVisualEditor(id, { novelId, dirty, busy, scope }), [id, novelId, dirty, busy, scope]);
  useEffect(() => {
    if (!dirty && !busy) return;
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [dirty, busy]);
}
