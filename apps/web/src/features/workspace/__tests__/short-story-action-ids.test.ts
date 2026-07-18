import assert from "node:assert/strict";
import test from "node:test";

import {
  classifyClientRequestFailure,
  StableClientRequestIds,
} from "../short-story/short-story-action-ids";

test("同一未决动作复用 ID，成功释放后下一次动作获得新 ID", () => {
  let sequence = 0;
  const ids = new StableClientRequestIds(() => `request-${++sequence}`);

  assert.equal(ids.get("outline:retry"), "request-1");
  assert.equal(ids.get("outline:retry"), "request-1");
  ids.release("outline:retry");
  assert.equal(ids.get("outline:retry"), "request-2");
  assert.equal(ids.get("outline:7:approve"), "request-3");
});

test("确认 HTTP 失败释放 ID，网络结果不确定时继续复用", () => {
  let sequence = 0;
  const ids = new StableClientRequestIds(() => `request-${++sequence}`);

  assert.equal(ids.get("decision:approve"), "request-1");
  ids.settle("decision:approve", "uncertain_network_error");
  assert.equal(ids.get("decision:approve"), "request-1");

  ids.settle("decision:approve", "confirmed_http_error");
  assert.equal(ids.get("decision:approve"), "request-2");

  ids.settle("decision:approve", "accepted");
  assert.equal(ids.get("decision:approve"), "request-3");
});

test("只有 4xx 是确定拒绝，5xx 与网络异常都保留原请求 ID", () => {
  assert.equal(classifyClientRequestFailure(400), "confirmed_http_error");
  assert.equal(classifyClientRequestFailure(409), "confirmed_http_error");
  assert.equal(classifyClientRequestFailure(499), "confirmed_http_error");
  assert.equal(classifyClientRequestFailure(500), "uncertain_network_error");
  assert.equal(classifyClientRequestFailure(503), "uncertain_network_error");
  assert.equal(classifyClientRequestFailure(undefined), "uncertain_network_error");
});
