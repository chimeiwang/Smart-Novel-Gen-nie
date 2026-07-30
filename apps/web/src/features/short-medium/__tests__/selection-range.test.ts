import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  buildSelectionIdentity,
  toCodePointRange,
} from "../selection-range";

describe("中短篇 Unicode 选区", () => {
  it("把 textarea UTF-16 下标转换为 Unicode 码点下标", () => {
    assert.deepEqual(toCodePointRange("甲😀乙", 1, 3), { start: 1, end: 2 });
  });

  it("保留中文、换行和辅助平面字符的原始选区", async () => {
    const content = "甲\n😀乙";
    const identity = await buildSelectionIdentity(content, 2, 4);

    assert.equal(identity.selectedText, "😀");
    assert.equal(identity.selectionStart, 2);
    assert.equal(identity.selectionEnd, 3);
    assert.match(identity.selectedTextHash, /^[0-9a-f]{64}$/);
  });

  it("拒绝空选区和拆开代理对的下标", () => {
    assert.throws(() => toCodePointRange("甲乙", 1, 1), /非空/);
    assert.throws(() => toCodePointRange("甲😀乙", 1, 2), /完整字符/);
  });
});
