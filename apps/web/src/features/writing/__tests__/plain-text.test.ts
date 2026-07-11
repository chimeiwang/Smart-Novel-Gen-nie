import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { normalizeParagraphTextDisplay, splitParagraphText } from "../plain-text";

describe("paragraph text display", () => {
  it("keeps markdown markers as literal text instead of treating them as formatting", () => {
    const input = "# Title\n\n- item\n\n**bold**";

    assert.equal(normalizeParagraphTextDisplay(input), input);
    assert.deepEqual(splitParagraphText(input), ["# Title", "- item", "**bold**"]);
  });

  it("unwraps legacy json envelopes without parsing normal text as markdown", () => {
    const input = JSON.stringify({ content: "Line one\n\n# literal heading" });

    assert.equal(normalizeParagraphTextDisplay(input), "Line one\n\n# literal heading");
  });
});
