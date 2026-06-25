import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { parseToolCallArguments } from "../tool-arguments";

describe("parseToolCallArguments", () => {
  it("returns a parse error instead of empty args for invalid JSON", () => {
    const result = parseToolCallArguments("{\"summary\":\"提交大纲草案\",\"updates\":");

    assert.equal(result.success, false);
    if (result.success) return;
    assert.match(result.error.message, /Unexpected end of JSON input/);
    assert.equal(result.error.rawArgumentsPreview, "{\"summary\":\"提交大纲草案\",\"updates\":");
  });

  it("accepts empty raw arguments only when the model explicitly returned an empty object", () => {
    const result = parseToolCallArguments("{}");

    assert.deepEqual(result, { success: true, args: {} });
  });

  it("does not guess-repair bare quotes inside JSON arguments", () => {
    const result = parseToolCallArguments(
      "{\"artifactKey\":\"outline\",\"updates\":{\"outlineAdjustments\":[{\"action\":\"update\",\"content\":\"第27章「绝望的积累」：纪寻说\"我继续查\"，然后离开。\"}]}}"
    );

    assert.equal(result.success, false);
  });
});
