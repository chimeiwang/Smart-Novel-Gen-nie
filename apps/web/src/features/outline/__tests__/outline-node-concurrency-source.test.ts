import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const source = readFileSync(
  join(process.cwd(), "src/features/outline/outline-panel.tsx"),
  "utf8",
);

test("大纲节点创建使用可重放请求标识", () => {
  assert.match(source, /createClientRequestId/);
  assert.match(source, /clientRequestId:\s*nodeClientRequestId/);
});

test("大纲节点更新和删除使用选中节点版本", () => {
  assert.match(source, /expectedUpdatedAt:\s*selectedNode\.updatedAt/);
  assert.match(
    source,
    /DELETE[\s\S]{0,260}body:\s*\{\s*expectedUpdatedAt:\s*selectedNode\.updatedAt\s*\}/,
  );
});

test("大纲节点业务请求体不重复发送路径 novelId", () => {
  assert.doesNotMatch(source, /const payload = \{\s*novelId,/);
});
