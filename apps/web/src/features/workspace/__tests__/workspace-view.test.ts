import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  buildWorkspaceChapterHref,
  parseWorkspaceView,
  resolveWorkspaceViewForProfile,
} from "../workspace-view";

describe("工作区视图", () => {
  it("只接受四个已声明工作区视图", () => {
    assert.equal(parseWorkspaceView("studio"), "studio");
    assert.equal(parseWorkspaceView("reading"), "reading");
    assert.equal(parseWorkspaceView("library"), "library");
    assert.equal(parseWorkspaceView("video"), "video");
  });

  it("缺失、数组或非法视图回退到 studio", () => {
    assert.equal(parseWorkspaceView(undefined), "studio");
    assert.equal(parseWorkspaceView(["reading"]), "studio");
    assert.equal(parseWorkspaceView("editor"), "studio");
    assert.equal(parseWorkspaceView("Reading"), "studio");
  });

  it("仅允许长篇进入视频制作视图", () => {
    assert.equal(resolveWorkspaceViewForProfile("video", "long_serial"), "video");
    assert.equal(resolveWorkspaceViewForProfile("video", "short_medium"), "studio");
    assert.equal(resolveWorkspaceViewForProfile("video", undefined), "studio");
    assert.equal(resolveWorkspaceViewForProfile("reading", "short_medium"), "reading");
  });

  it("章节链接同时保留目标章节和当前视图", () => {
    assert.equal(
      buildWorkspaceChapterHref({
        novelId: "novel / 一",
        chapterId: "chapter ? 二",
        view: "reading",
      }),
      "/workspace/novel%20%2F%20%E4%B8%80?chapterId=chapter+%3F+%E4%BA%8C&view=reading",
    );
  });
});
