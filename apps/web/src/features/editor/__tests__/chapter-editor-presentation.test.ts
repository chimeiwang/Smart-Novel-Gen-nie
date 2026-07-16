import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { getChapterEditorPresentation } from "../chapter-editor-presentation";

describe("章节阅读与小修展示", () => {
  it("阅读视图的草稿默认只展示正文", () => {
    assert.deepEqual(
      getChapterEditorPresentation({
        view: "reading",
        chapterStatus: "drafting",
        minorEditing: false,
      }),
      {
        showEditableFields: false,
        showReadingContent: true,
        showEnterMinorEdit: true,
        readOnlyReason: null,
      },
    );
  });

  it("点击进入小修后才展示编辑字段", () => {
    assert.deepEqual(
      getChapterEditorPresentation({
        view: "reading",
        chapterStatus: "drafting",
        minorEditing: true,
      }),
      {
        showEditableFields: true,
        showReadingContent: false,
        showEnterMinorEdit: false,
        readOnlyReason: null,
      },
    );
  });

  it("审核和已完成章节显示明确只读原因", () => {
    assert.match(
      getChapterEditorPresentation({
        view: "reading",
        chapterStatus: "review",
        minorEditing: false,
      }).readOnlyReason ?? "",
      /审核/,
    );
    assert.match(
      getChapterEditorPresentation({
        view: "reading",
        chapterStatus: "completed",
        minorEditing: false,
      }).readOnlyReason ?? "",
      /完成/,
    );
  });
});
