import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  buildWorkspaceViewHref,
  commitWorkspaceViewChange,
  parseWorkspaceViewFromSearch,
} from "../workspace-shell-state";

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
        currentView: "studio",
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

  it("其他视图之间切换也先 flush", async () => {
    const events: string[] = [];

    await commitWorkspaceViewChange({
      currentView: "studio",
      nextView: "library",
      flush: async () => {
        events.push("flush");
      },
      commit: (view) => {
        events.push(`commit:${view}`);
      },
    });

    assert.deepEqual(events, ["flush", "commit:library"]);
  });

  it("从浏览器查询参数恢复合法视图", () => {
    assert.equal(parseWorkspaceViewFromSearch("?chapterId=c1&view=reading"), "reading");
    assert.equal(parseWorkspaceViewFromSearch("?view=library"), "library");
    assert.equal(parseWorkspaceViewFromSearch("?view=unknown"), "studio");
    assert.equal(parseWorkspaceViewFromSearch("?chapterId=c1"), "studio");
  });

  it("保存失败后保留其他查询参数并恢复当前视图 URL", () => {
    assert.equal(
      buildWorkspaceViewHref(
        "https://inkforge.test/workspace/n1?chapterId=c2&view=library",
        "reading",
      ),
      "https://inkforge.test/workspace/n1?chapterId=c2&view=reading",
    );
  });
});
