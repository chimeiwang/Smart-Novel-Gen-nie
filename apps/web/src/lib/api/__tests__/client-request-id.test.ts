import assert from "node:assert/strict";
import test from "node:test";

import { createClientRequestId } from "../client-request-id";

test("原生 randomUUID 可用时优先使用原生实现", () => {
  let fallbackCalled = false;
  const expected = "11111111-1111-4111-8111-111111111111";

  const actual = createClientRequestId({
    randomUUID: () => expected,
    getRandomValues: (bytes) => {
      fallbackCalled = true;
      return bytes;
    },
  });

  assert.equal(actual, expected);
  assert.equal(fallbackCalled, false);
});

test("缺少 randomUUID 时使用随机字节生成 UUID v4", () => {
  const actual = createClientRequestId({
    getRandomValues: (bytes) => {
      bytes.fill(0xff);
      return bytes;
    },
  });

  assert.equal(actual, "ffffffff-ffff-4fff-bfff-ffffffffffff");
  assert.match(actual, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});
