/**
 * API 错误契约测试。
 *
 * 运行方式：npx tsx --test src/shared/contracts/__tests__/api-error.test.ts
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { z } from "zod";
import { formatZodIssues } from "../api-error";

describe("api error contract", () => {
  it("把 Zod 校验错误转换成稳定路径和中文消息", () => {
    const result = z.object({
      taskId: z.string().min(1, "缺少写作任务"),
    }).safeParse({ taskId: "" });

    assert.equal(result.success, false);
    if (!result.success) {
      assert.deepEqual(formatZodIssues(result.error), [
        { path: "taskId", message: "缺少写作任务" },
      ]);
    }
  });
});
