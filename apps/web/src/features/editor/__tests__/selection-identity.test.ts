import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  buildSelectionAttachment,
  buildSelectionRunRequest,
  isSelectionAttachmentStale,
  selectionPreview,
  type SelectionAttachment,
} from "../selection-identity";

describe("显式选区附件身份", () => {
  it("按 Unicode 码点记录章节选区，并保留正文 hash", async () => {
    const attachment = await buildSelectionAttachment({
      resourceType: "chapter_content",
      resourceId: "chapter-1",
      sourceLabel: "第 1 章",
      baseUpdatedAt: "2026-08-10T00:00:00Z",
      content: "甲😀乙\n丙",
      utf16Start: 1,
      utf16End: 3,
    });

    assert.equal(attachment.selectionStart, 1);
    assert.equal(attachment.selectionEnd, 2);
    assert.equal(attachment.selectedText, "😀");
    assert.equal(attachment.baseContentHash.length, 64);
    assert.equal(attachment.selectedTextHash.length, 64);
  });

  it("区分总纲和大纲节点身份，发送体不携带 selectedText", async () => {
    const node = await buildSelectionAttachment({
      resourceType: "outline_node_content",
      resourceId: "node-7",
      sourceLabel: "总纲 / 第一幕 / 节点 7",
      baseUpdatedAt: "2026-08-10T00:00:00Z",
      content: "节点内容",
      utf16Start: 0,
      utf16End: 2,
    });
    const body = buildSelectionRunRequest({
      attachment: node,
      novelId: "novel-1",
      chapterId: "chapter-1",
      writingSessionId: "session-1",
      targetWordCount: 4000,
      userInstruction: "改得更紧凑",
    });

    assert.equal(body.operation, "rewrite_outline_selection");
    assert.equal(body.selectionTarget?.resourceType, "outline_node_content");
    assert.equal(body.scope.kind, "outline_node");
    assert.equal("selectedText" in body, false);
    assert.equal("selectedText" in body.selectionTarget!, false);
  });

  it("来源内容或版本改变时附件必须重新选择", async () => {
    const attachment = await buildSelectionAttachment({
      resourceType: "outline_content",
      resourceId: "novel-1",
      sourceLabel: "总纲",
      baseUpdatedAt: "2026-08-10T00:00:00Z",
      content: "原始总纲",
      utf16Start: 0,
      utf16End: 2,
    });

    assert.equal(isSelectionAttachmentStale(attachment, {
      updatedAt: "2026-08-10T00:00:00Z",
      content: "原始总纲",
    }), false);
    assert.equal(isSelectionAttachmentStale(attachment, {
      updatedAt: "2026-08-10T00:01:00Z",
      content: "原始总纲",
    }), true);
    assert.equal(isSelectionAttachmentStale(attachment, {
      updatedAt: "2026-08-10T00:00:00Z",
      content: "修改后总纲",
    }), true);
  });

  it("长选区预览同时保留开头和结尾", () => {
    assert.equal(selectionPreview("一二三四五六七八九十", 6), "一二三…八九十");
  });
});
