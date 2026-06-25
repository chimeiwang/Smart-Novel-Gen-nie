// @2.3
export function countTextLength(text: string) {
  return text.replace(/\s+/g, "").length;
}
