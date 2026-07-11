import assert from "node:assert/strict";
import test from "node:test";

import { CoreApiPageError, requireApiData } from "../response";

test("成功响应返回类型化数据", () => {
  const data = requireApiData({
    data: { novels: [] },
    response: new Response(null, { status: 200 }),
  });

  assert.deepEqual(data, { novels: [] });
});

test("失败响应保留状态码和核心服务中文消息", () => {
  assert.throws(
    () =>
      requireApiData({
        error: { code: "forbidden", message: "无权访问该作品" },
        response: new Response(null, { status: 403 }),
      }),
    (error) => {
      assert.ok(error instanceof CoreApiPageError);
      assert.equal(error.status, 403);
      assert.equal(error.message, "无权访问该作品");
      return true;
    },
  );
});

test("未知错误使用稳定中文消息", () => {
  assert.throws(
    () =>
      requireApiData({
        error: {},
        response: new Response(null, { status: 404 }),
      }),
    (error) => {
      assert.ok(error instanceof CoreApiPageError);
      assert.equal(error.status, 404);
      assert.equal(error.message, "请求核心服务失败");
      return true;
    },
  );
});

test("无响应体的 204 仍然视为成功", () => {
  const result = requireApiData({
    response: new Response(null, { status: 204 }),
  });

  assert.equal(result, undefined);
});
