import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { commitWorkspaceViewChange } from "../workspace-shell-state";

describe("工作区视图切换", () => {
  it("离开阅读视图前先 flush，成功后才提交视图", async () => {
    const events: string[] = [];

    await commitWorkspaceViewChange({
      currentView: "reading",
      nextView: "studio",
      flush: async () => {
        events.push("flush");
      },
      commit: (view) => {
        events.push(`commit:${view}`);
      },
    });

    assert.deepEqual(events, ["flush", "commit:studio"]);
  });

  it("flush 失败时不提交新视图", async () => {
    let committed = false;

    await assert.rejects(
      commitWorkspaceViewChange({
        currentView: "reading",
        nextView: "library",
        flush: async () => {
          throw new Error("保存失败");
        },
        commit: () => {
          committed = true;
        },
      }),
      /保存失败/,
    );

    assert.equal(committed, false);
  });

  it("其他视图之间切换不 flush", async () => {
    let flushCount = 0;
    let committedView = "";

    await commitWorkspaceViewChange({
      currentView: "studio",
      nextView: "library",
      flush: async () => {
        flushCount += 1;
      },
      commit: (view) => {
        committedView = view;
      },
    });

    assert.equal(flushCount, 0);
    assert.equal(committedView, "library");
  });
});
