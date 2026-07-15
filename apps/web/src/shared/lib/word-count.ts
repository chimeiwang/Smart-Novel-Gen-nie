const IGNORED_TEXT_CHARACTERS = /[\u0009-\u000d\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]/gu;

/** 排除 Unicode 空白和 BOM，并按 Unicode 码点统计。 */
export function countTextLength(text: string) {
  return Array.from(text.replace(IGNORED_TEXT_CHARACTERS, "")).length;
}
