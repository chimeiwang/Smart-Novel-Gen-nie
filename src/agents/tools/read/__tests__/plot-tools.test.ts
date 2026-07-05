import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  getOutlineNodeExecutor,
  getRecentChaptersExecutor,
  listOutlineSummaryExecutor,
} from "../plot-tools";

function state(novelData: Record<string, unknown>) {
  return { novelData };
}

describe("剧情只读工具的大纲与章节边界", () => {
  it("写作态 list_outline_summary 只返回当前章路径和完整章节组", async () => {
    const tail = "CURRENT_GROUP_TAIL_SENTINEL";
    const output = await listOutlineSummaryExecutor({}, state({
      writingOutlineContext: {
        status: "resolved",
        source: "chapter_group",
        targetChapter: { id: "c20", order: 20, title: "第20章" },
        path: [
          { id: "s2", title: "第二阶段", kind: "stage", chapterStartOrder: 16, chapterEndOrder: 40 },
          { id: "u2", title: "追查", kind: "plot_unit", chapterStartOrder: 16, chapterEndOrder: 25 },
          {
            id: "g20",
            title: "第20-25章",
            kind: "chapter_group",
            chapterStartOrder: 20,
            chapterEndOrder: 25,
            content: `当前章节组完整正文 ${tail}`,
          },
        ],
      },
      outlineNodes: [{ id: "future", title: "第21-90章", content: "FUTURE_DETAIL" }],
    }));

    assert.match(output, new RegExp(tail));
    assert.doesNotMatch(output, /FUTURE_DETAIL/);
    assert.match(output, /不是字符截断/);
  });

  it("get_outline_node 标题匹配多条时明确报错", async () => {
    const output = await getOutlineNodeExecutor({ node_title: "调查" }, state({
      outlineNodes: [
        { id: "u1", title: "调查开始" },
        { id: "u2", title: "深入调查" },
      ],
    }));
    const parsed = JSON.parse(output);

    assert.equal(parsed.error, "OUTLINE_NODE_AMBIGUOUS");
    assert.deepEqual(parsed.candidates.map((item: { id: string }) => item.id), ["u1", "u2"]);
  });

  it("get_recent_chapters 按目标第6章选择到第5章并完整保留正文末尾", async () => {
    const tail = "CHAPTER_FIVE_TAIL_SENTINEL";
    const chapters = Array.from({ length: 6 }, (_, index) => ({
      id: `c${index + 1}`,
      title: `第${index + 1}章`,
      order: index + 1,
      content: index === 4 ? `第五章完整正文${"长".repeat(1000)}${tail}` : `第${index + 1}章正文`,
    }));
    const output = await getRecentChaptersExecutor({ count: 2 }, state({
      chapterId: "c2",
      targetChapterOrder: 6,
      chapters,
    }));
    const parsed = JSON.parse(output);

    assert.deepEqual(parsed.chapters.map((chapter: { order: number }) => chapter.order), [4, 5]);
    assert.match(parsed.chapters[1].content, new RegExp(`${tail}$`));
    assert.match(parsed.note, /未做字符裁剪/);
  });
});
