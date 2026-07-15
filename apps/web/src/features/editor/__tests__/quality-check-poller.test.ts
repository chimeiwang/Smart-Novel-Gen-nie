import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  canResetQualityCheck,
  findRunningQualityCheck,
  findQualityCheckToResume,
  pollQualityCheck,
} from "../quality-check-poller";

type Check = { id: string; status: string };

describe("pollQualityCheck", () => {
  it("持续轮询 pending/running 并返回终态", async () => {
    const statuses = ["pending", "running", "completed"];
    const updates: string[] = [];
    const waits: number[] = [];

    const result = await pollQualityCheck<Check>({
      fetchCheck: async () => ({ id: "check-1", status: statuses.shift() ?? "completed" }),
      getStatus: (check) => check.status,
      onUpdate: (check) => updates.push(check.status),
      wait: async (milliseconds) => {
        waits.push(milliseconds);
      },
      maxAttempts: 5,
    });

    assert.equal(result?.status, "completed");
    assert.deepEqual(updates, ["pending", "running", "completed"]);
    assert.equal(waits.length, 2);
    assert.ok(waits[1]! >= waits[0]!);
  });

  it("组件取消后停止下一次请求", async () => {
    let cancelled = false;
    let calls = 0;

    const result = await pollQualityCheck<Check>({
      fetchCheck: async () => {
        calls += 1;
        return { id: "check-1", status: "running" };
      },
      getStatus: (check) => check.status,
      wait: async () => {
        cancelled = true;
      },
      isCancelled: () => cancelled,
      maxAttempts: 5,
    });

    assert.equal(result, null);
    assert.equal(calls, 1);
  });

  it("超过轮询上限时明确失败", async () => {
    await assert.rejects(
      pollQualityCheck<Check>({
        fetchCheck: async () => ({ id: "check-1", status: "running" }),
        getStatus: (check) => check.status,
        wait: async () => undefined,
        maxAttempts: 2,
      }),
      /轮询超时/,
    );
  });
});

describe("findQualityCheckToResume", () => {
  const checks = [
    { id: "pending", status: "pending" },
    { id: "running", status: "running" },
  ];

  it("页面恢复时选择唯一的运行中检查", () => {
    assert.deepEqual(findQualityCheckToResume(checks, null, null), checks[1]);
  });

  it("已有轮询或同一检查已恢复时不重复启动", () => {
    assert.equal(findQualityCheckToResume(checks, "running", null), null);
    assert.equal(findQualityCheckToResume(checks, null, "running"), null);
  });
});

describe("findRunningQualityCheck", () => {
  it("轮询失败后允许用户显式重新查询仍在运行的检查", () => {
    const checks = [{ id: "running", status: "running" }];

    assert.deepEqual(findRunningQualityCheck(checks, null), checks[0]);
    assert.equal(findRunningQualityCheck(checks, "running"), null);
  });
});

describe("canResetQualityCheck", () => {
  it("仅允许未完成章节重置已跳过的检查", () => {
    assert.equal(canResetQualityCheck("review", "skipped"), true);
    assert.equal(canResetQualityCheck("completed", "skipped"), false);
    assert.equal(canResetQualityCheck("review", "completed"), false);
  });
});
