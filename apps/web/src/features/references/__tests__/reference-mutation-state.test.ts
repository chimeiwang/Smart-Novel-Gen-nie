import assert from "node:assert/strict";
import test from "node:test";

import {
  advanceReferenceCreateIdentity,
  buildReferenceDeleteBody,
  buildReferenceUpdateBody,
  createReferenceMutationState,
} from "../reference-mutation-state";

test("参考资料创建失败重试复用身份且成功后才更换", () => {
  const ids = ["reference-create-0001", "reference-create-0002"];
  const factory = () => ids.shift() ?? "unexpected";
  const initial = createReferenceMutationState(factory);

  assert.equal(initial.clientRequestId, "reference-create-0001");
  assert.equal(initial.clientRequestId, "reference-create-0001");
  assert.equal(
    advanceReferenceCreateIdentity(initial, false, factory).clientRequestId,
    "reference-create-0001",
  );
  assert.equal(
    advanceReferenceCreateIdentity(initial, true, factory).clientRequestId,
    "reference-create-0002",
  );
});

test("参考资料更新删除使用目标 DTO 的版本且保留 ragStatus", () => {
  const reference = { id: "ref-1", updatedAt: "2026-08-07T08:00:00Z", ragStatus: "disabled" as const };

  assert.deepEqual(buildReferenceUpdateBody(reference, { title: "新标题" }), {
    title: "新标题",
    expectedUpdatedAt: reference.updatedAt,
  });
  assert.deepEqual(buildReferenceDeleteBody(reference), {
    expectedUpdatedAt: reference.updatedAt,
  });
  assert.equal(reference.ragStatus, "disabled");
});
