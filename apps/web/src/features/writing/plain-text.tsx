type MessageLike = {
  agentId?: string;
  content: string;
  isNewProtocol?: boolean;
};

function decodeQuotedJsonString(content: string, startIndex: number): string | null {
  let value = "";
  let escaped = false;
  let unicodeEscape: string | null = null;

  for (let index = startIndex; index < content.length; index++) {
    const ch = content[index];

    if (unicodeEscape !== null) {
      unicodeEscape += ch;
      if (unicodeEscape.length === 4) {
        const code = parseInt(unicodeEscape, 16);
        value += Number.isNaN(code) ? `\\u${unicodeEscape}` : String.fromCharCode(code);
        unicodeEscape = null;
        escaped = false;
      }
      continue;
    }

    if (escaped) {
      const map: Record<string, string> = {
        "\"": "\"",
        "\\": "\\",
        "/": "/",
        b: "\b",
        f: "\f",
        n: "\n",
        r: "\r",
        t: "\t",
      };
      if (ch === "u") {
        unicodeEscape = "";
      } else {
        value += map[ch] ?? ch;
        escaped = false;
      }
      continue;
    }

    if (ch === "\\") {
      escaped = true;
      continue;
    }

    if (ch === "\"") {
      return value;
    }

    value += ch;
  }

  return null;
}

function extractJsonStringField(content: string, fieldName: string): string | null {
  const pattern = new RegExp(`"${fieldName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"\\s*:\\s*"`);
  const match = pattern.exec(content);
  if (!match || match.index === undefined) return null;
  return decodeQuotedJsonString(content, match.index + match[0].length);
}

export function normalizeParagraphTextDisplay(content: string, agentId?: string): string {
  const trimmed = content.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("```json")) {
    return content;
  }

  const candidates: string[] = [];
  const codeBlockMatch = content.match(/```json\s*([\s\S]*?)\s*```/g);
  if (codeBlockMatch) {
    for (const block of codeBlockMatch) {
      const inner = block.replace(/```json\s*|\s*```/g, "").trim();
      if (inner) candidates.push(inner);
    }
  }

  const lastBrace = content.lastIndexOf("}");
  if (lastBrace > 0) {
    const firstBrace = content.indexOf("{");
    if (firstBrace >= 0 && firstBrace < lastBrace) {
      candidates.push(content.slice(firstBrace, lastBrace + 1));
    }
  }

  candidates.push(trimmed);

  for (const candidate of candidates) {
    try {
      const parsed = JSON.parse(candidate);
      if (agentId === "写作") {
        const parts: string[] = [];
        if (typeof parsed.content === "string" && parsed.content.trim().length > 0) {
          parts.push(parsed.content);
        }
        if (typeof parsed.generatedContent === "string" && parsed.generatedContent.trim().length > 0) {
          parts.push(parsed.generatedContent);
        }
        if (parts.length > 0) return parts.join("\n\n");
      }
      if (typeof parsed.content === "string" && parsed.content.trim().length > 0) {
        return parsed.content;
      }
    } catch {
      const loose = extractJsonStringField(candidate, "content");
      if (loose && loose.trim().length > 0) {
        return loose;
      }
    }
  }

  return content;
}

export function renderParagraphMessageContent(message: MessageLike): string {
  if (message.isNewProtocol) {
    return message.content;
  }
  return normalizeParagraphTextDisplay(message.content, message.agentId);
}

export function splitParagraphText(content: string): string[] {
  return content
    .replace(/\r\n/g, "\n")
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
}

export function ParagraphText({ text }: { text: string }) {
  const paragraphs = splitParagraphText(text);
  if (paragraphs.length === 0) return null;

  return (
    <div className="paragraph-text">
      {paragraphs.map((paragraph, index) => (
        <p key={index}>{paragraph}</p>
      ))}
    </div>
  );
}
