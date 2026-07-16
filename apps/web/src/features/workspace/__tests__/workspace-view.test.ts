import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  buildWorkspaceChapterHref,
  parseWorkspaceView,
} from "../workspace-view";

describe("工作区视图", () => {
  it("只接受 studio、reading 和 library", () => {
    assert.equal(parseWorkspaceView("studio"), "studio");
    assert.equal(parseWorkspaceView("reading"), "reading");
    assert.equal(parseWorkspaceView("library"), "library");
  });

  it("缺失、数组或非法视图回退到 studio", () => {
    assert.equal(parseWorkspaceView(undefined), "studio");
    assert.equal(parseWorkspaceView(["reading"]), "studio");
    assert.equal(parseWorkspaceView("editor"), "studio");
    assert.equal(parseWorkspaceView("Reading"), "studio");
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
