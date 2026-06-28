import { afterEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { prisma } from "@/shared/db/prisma";
import { resolveChapterDraftTarget } from "../chapter-target-resolver";

const originalFindMany = prisma.chapter.findMany.bind(prisma.chapter);

afterEach(() => {
  Object.assign(prisma.chapter, { findMany: originalFindMany });
});

function mockChapters(chapters: Array<{
  id: string;
  title: string;
  order: number;
  status: "drafting" | "review" | "completed";
  content: string;
}>) {
  Object.assign(prisma.chapter, {
    findMany: async () => chapters,
  });
}

describe("chapter target resolver", () => {
  it("已落库章节继续写作时生成下一章草案目标", async () => {
    mockChapters([
      { id: "c1", title: "第一章", order: 1, status: "completed", content: "第一章正文" },
    ]);

    const result = await resolveChapterDraftTarget({
      novelId: "n1",
      chapterId: "c1",
      userMessage: "按计划写正文",
    });

    assert.deepEqual(result.target, {
      mode: "new_next_chapter",
      afterChapterId: "c1",
      title: "第 2 章",
    });
    assert.equal(result.targetContent, "");
  });

  it("已有空后续草稿章时写入该章节", async () => {
    mockChapters([
      { id: "c1", title: "第一章", order: 1, status: "review", content: "第一章正文" },
      { id: "c2", title: "第二章", order: 2, status: "drafting", content: "" },
    ]);

    const result = await resolveChapterDraftTarget({
      novelId: "n1",
      chapterId: "c1",
      userMessage: "继续写",
    });

    assert.deepEqual(result.target, { mode: "existing_chapter", chapterId: "c2" });
    assert.equal(result.targetTitle, "第二章");
  });

  it("明确要求重写当前章时保留当前章节", async () => {
    mockChapters([
      { id: "c1", title: "第一章", order: 1, status: "completed", content: "第一章正文" },
    ]);

    const result = await resolveChapterDraftTarget({
      novelId: "n1",
      chapterId: "c1",
      userMessage: "重写第一章",
    });

    assert.deepEqual(result.target, { mode: "existing_chapter", chapterId: "c1" });
  });

  it("规划章节不会创建不存在的新章节目标", async () => {
    mockChapters([
      { id: "c1", title: "第一章", order: 1, status: "completed", content: "第一章正文" },
    ]);

    const result = await resolveChapterDraftTarget({
      novelId: "n1",
      chapterId: "c1",
      userMessage: "规划本章",
      allowNewChapterTarget: false,
    });

    assert.deepEqual(result.target, { mode: "existing_chapter", chapterId: "c1" });
  });
});
