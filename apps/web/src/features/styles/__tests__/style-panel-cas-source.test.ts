import assert from "node:assert/strict";
import test from "node:test";

import { buildApplyStyleBody } from "../style-mutation";

test("文风应用与清除都使用 resources GET 当前应用值", () => {
  assert.deepEqual(buildApplyStyleBody("new", "current"), {
    styleId: "new",
    expectedStyleId: "current",
  });
  assert.deepEqual(buildApplyStyleBody(null, "current"), {
    styleId: null,
    expectedStyleId: "current",
  });
  assert.deepEqual(buildApplyStyleBody("new", null), {
    styleId: "new",
    expectedStyleId: null,
  });
});
