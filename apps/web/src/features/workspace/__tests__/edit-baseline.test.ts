import assert from "node:assert/strict";
import test from "node:test";

import {
  captureEditBaseline,
  requireEditBaseline,
} from "../edit-baseline";

test("五类设定打开 v1 后即使 props 变为 v2 仍使用冻结版本", () => {
  for (const kind of ["characters", "items", "locations", "factions", "glossaries"] as const) {
    const baseline = captureEditBaseline({
      id: `${kind}-1`,
      kind,
      updatedAt: "v1",
      name: "旧表单",
    });
    const refreshed = { ...baseline.value, updatedAt: "v2", name: "服务端新值" };

    assert.equal(refreshed.updatedAt, "v2");
    assert.equal(requireEditBaseline(`${kind}-1`, baseline).updatedAt, "v1");
    assert.equal(requireEditBaseline(`${kind}-1`, baseline).name, "旧表单");
  }
});

test("角色基线深拷贝经历关系的版本和业务字段", () => {
  const opened = {
    id: "character-1",
    updatedAt: "parent-v1",
    experiences: [{ id: "exp-1", updatedAt: "exp-v1", content: "旧经历" }],
    relations: [{ id: "rel-1", updatedAt: "rel-v1", description: "旧关系" }],
  };
  const baseline = captureEditBaseline(opened);

  opened.updatedAt = "parent-v2";
  opened.experiences[0].updatedAt = "exp-v2";
  opened.experiences[0].content = "服务端新经历";
  opened.relations[0].updatedAt = "rel-v2";
  opened.relations[0].description = "服务端新关系";

  const frozen = requireEditBaseline("character-1", baseline);
  assert.equal(frozen.updatedAt, "parent-v1");
  assert.deepEqual(frozen.experiences, [
    { id: "exp-1", updatedAt: "exp-v1", content: "旧经历" },
  ]);
  assert.deepEqual(frozen.relations, [
    { id: "rel-1", updatedAt: "rel-v1", description: "旧关系" },
  ]);
});

test("参考资料编辑冻结 v1 且目标从 props 消失后仍不会变成创建", () => {
  const baseline = captureEditBaseline({
    id: "reference-1",
    updatedAt: "v1",
    title: "旧标题",
    content: "旧正文",
  });

  assert.equal(requireEditBaseline("reference-1", baseline).updatedAt, "v1");
  assert.throws(
    () => requireEditBaseline("reference-1", null),
    /编辑基线缺失/,
  );
  assert.throws(
    () => requireEditBaseline("reference-2", baseline),
    /编辑基线不匹配/,
  );
  assert.equal(requireEditBaseline(null, baseline), null);
});
