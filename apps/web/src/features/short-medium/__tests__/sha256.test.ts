import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { sha256Text } from "../sha256";

describe("HTTP 兼容 SHA-256", () => {
  it("缺少 SubtleCrypto 时通过标准测试向量", async () => {
    assert.equal(
      await sha256Text("", {}),
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    );
    assert.equal(
      await sha256Text("abc", {}),
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );
    assert.equal(
      await sha256Text("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq", {}),
      "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1",
    );
  });

  it("中文、换行和 Emoji 的回退结果与原生实现一致", async () => {
    const value = "甲\n😀乙";
    const native = await sha256Text(value, { subtle: globalThis.crypto.subtle });
    const fallback = await sha256Text(value, {});

    assert.equal(fallback, "02ae515aa43f12a34a9001e599247e7723305772c423f67360c0de5e5fc097bb");
    assert.equal(fallback, native);
  });

  it("优先使用可用的原生 digest", async () => {
    let called = false;
    const digest = new Uint8Array(32).fill(0xab).buffer;

    const actual = await sha256Text("abc", {
      subtle: {
        digest: async () => {
          called = true;
          return digest;
        },
      },
    });

    assert.equal(called, true);
    assert.equal(actual, "ab".repeat(32));
  });

  it("填充边界两侧的回退结果与原生实现一致", async () => {
    for (const value of ["a".repeat(55), "a".repeat(56), "a".repeat(64)]) {
      const native = await sha256Text(value, { subtle: globalThis.crypto.subtle });
      const fallback = await sha256Text(value, {});
      assert.equal(fallback, native);
    }
  });
});
