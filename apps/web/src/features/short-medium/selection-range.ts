import { sha256Text } from "./sha256";

export type CodePointRange = {
  start: number;
  end: number;
};

export type SelectionIdentity = {
  selectionStart: number;
  selectionEnd: number;
  selectedText: string;
  selectedTextHash: string;
};

function isHighSurrogate(value: number): boolean {
  return value >= 0xd800 && value <= 0xdbff;
}

function isLowSurrogate(value: number): boolean {
  return value >= 0xdc00 && value <= 0xdfff;
}

function splitsSurrogatePair(content: string, index: number): boolean {
  if (index <= 0 || index >= content.length) return false;
  return (
    isHighSurrogate(content.charCodeAt(index - 1)) &&
    isLowSurrogate(content.charCodeAt(index))
  );
}

export function toCodePointRange(
  content: string,
  utf16Start: number,
  utf16End: number,
): CodePointRange {
  if (
    !Number.isInteger(utf16Start) ||
    !Number.isInteger(utf16End) ||
    utf16Start < 0 ||
    utf16End > content.length
  ) {
    throw new Error("选区位置超出正文范围");
  }
  if (utf16Start >= utf16End) {
    throw new Error("请选择非空文本");
  }
  if (
    splitsSurrogatePair(content, utf16Start) ||
    splitsSurrogatePair(content, utf16End)
  ) {
    throw new Error("选区边界必须落在完整字符之间");
  }
  return {
    start: Array.from(content.slice(0, utf16Start)).length,
    end: Array.from(content.slice(0, utf16End)).length,
  };
}

export { sha256Text };

export async function buildSelectionIdentity(
  content: string,
  utf16Start: number,
  utf16End: number,
): Promise<SelectionIdentity> {
  const range = toCodePointRange(content, utf16Start, utf16End);
  const selectedText = content.slice(utf16Start, utf16End);
  return {
    selectionStart: range.start,
    selectionEnd: range.end,
    selectedText,
    selectedTextHash: await sha256Text(selectedText),
  };
}
