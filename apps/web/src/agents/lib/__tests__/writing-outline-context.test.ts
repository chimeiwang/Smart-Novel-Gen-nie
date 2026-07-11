import { describe, it } from "node:test";
import assert from "node:assert/strict";
import type { OutlineNodeData } from "@/agents/graph/state";
import { resolveWritingOutlineContext } from "../writing-outline-context";

function node(input: Partial<OutlineNodeData> & Pick<OutlineNodeData, "id" | "title" | "kind">): OutlineNodeData {
  return {
    status: "planned",
    order: 0,
    ...input,
  };
}

describe("resolveWritingOutlineContext", () => {
  it("第20章只选择当前路径和完整章节组，不带未来节点", () => {
    const tail = "CURRENT_GROUP_TAIL_SENTINEL";
    const nodes: OutlineNodeData[] = [
      node({ id: "s1", title: "第二阶段", kind: "stage", chapterStartOrder: 16, chapterEndOrder: 40 }),
      node({ id: "u1", parentId: "s1", title: "主动追查", kind: "plot_unit", chapterStartOrder: 16, chapterEndOrder: 25 }),
      node({ id: "g1", parentId: "u1", title: "第20-25章", kind: "chapter_group", chapterStartOrder: 20, chapterEndOrder: 25, content: `当前组完整内容 ${tail}` }),
      node({ id: "g2", parentId: "u1", title: "第26-30章", kind: "chapter_group", chapterStartOrder: 26, chapterEndOrder: 30, content: "FUTURE_CONTENT" }),
    ];

    const result = resolveWritingOutlineContext({
      outlineNodes: nodes,
      targetChapter: { id: "c20", order: 20, title: "第20章" },
      hasApprovedBeatPlan: false,
      hasChapterWritingGoal: false,
    });

    assert.equal(result.status, "resolved");
    assert.equal(result.source, "chapter_group");
    assert.deepEqual(result.path.map((item) => item.id), ["s1", "u1", "g1"]);
    assert.match(result.path[2].content ?? "", new RegExp(tail));
    assert.doesNotMatch(JSON.stringify(result), /FUTURE_CONTENT/);
  });

  it("未来节点数量增加不改变第20章上下文", () => {
    const base: OutlineNodeData[] = [
      node({ id: "s1", title: "阶段", kind: "stage", chapterStartOrder: 1, chapterEndOrder: 2000 }),
      node({ id: "u1", parentId: "s1", title: "单元", kind: "plot_unit", chapterStartOrder: 1, chapterEndOrder: 25 }),
      node({ id: "g1", parentId: "u1", title: "当前组", kind: "chapter_group", chapterStartOrder: 20, chapterEndOrder: 20, content: "当前完整内容" }),
    ];
    const input = {
      targetChapter: { id: "c20", order: 20, title: "第20章" },
      hasApprovedBeatPlan: false,
      hasChapterWritingGoal: false,
    };
    const before = resolveWritingOutlineContext({ ...input, outlineNodes: base });
    const future = Array.from({ length: 500 }, (_, index) => node({
      id: `future-${index}`,
      parentId: "u1",
      title: `未来${index}`,
      kind: "chapter_group",
      chapterStartOrder: 100 + index,
      chapterEndOrder: 100 + index,
      content: `未来内容${index}`,
    }));
    const after = resolveWritingOutlineContext({ ...input, outlineNodes: [...base, ...future] });
    assert.deepEqual(after, before);
  });

  it("重叠章节组返回 ambiguous，不随机选择", () => {
    const result = resolveWritingOutlineContext({
      outlineNodes: [
        node({ id: "g1", title: "版本一", kind: "chapter_group", chapterStartOrder: 18, chapterEndOrder: 22 }),
        node({ id: "g2", title: "版本二", kind: "chapter_group", chapterStartOrder: 20, chapterEndOrder: 25 }),
      ],
      targetChapter: { id: "c20", order: 20, title: "第20章" },
      hasApprovedBeatPlan: false,
      hasChapterWritingGoal: false,
    });
    assert.equal(result.status, "ambiguous");
    assert.deepEqual(result.candidateIds, ["g1", "g2"]);
  });

  it("approved Beat Plan 优先时不注入章节组长内容", () => {
    const result = resolveWritingOutlineContext({
      outlineNodes: [
        node({ id: "s1", title: "阶段", kind: "stage", chapterStartOrder: 1, chapterEndOrder: 30 }),
        node({ id: "u1", parentId: "s1", title: "单元", kind: "plot_unit", chapterStartOrder: 1, chapterEndOrder: 10 }),
        node({ id: "g1", parentId: "u1", title: "章节组", kind: "chapter_group", chapterStartOrder: 6, chapterEndOrder: 7, content: "不应重复注入" }),
      ],
      targetChapter: { id: "c6", order: 6, title: "第6章" },
      hasApprovedBeatPlan: true,
      hasChapterWritingGoal: true,
    });
    assert.equal(result.source, "approved_beat_plan");
    assert.equal(result.path[2].content, undefined);
  });

  it("没有 Beat Plan 时 ChapterWritingGoal 优先于章节组正文", () => {
    const result = resolveWritingOutlineContext({
      outlineNodes: [
        node({ id: "s1", title: "阶段", kind: "stage", chapterStartOrder: 1, chapterEndOrder: 30 }),
        node({ id: "u1", parentId: "s1", title: "单元", kind: "plot_unit", chapterStartOrder: 1, chapterEndOrder: 10 }),
        node({ id: "g1", parentId: "u1", title: "章节组", kind: "chapter_group", chapterStartOrder: 6, chapterEndOrder: 7, content: "不应重复注入" }),
      ],
      targetChapter: { id: "c6", order: 6, title: "第6章" },
      hasApprovedBeatPlan: false,
      hasChapterWritingGoal: true,
    });
    assert.equal(result.source, "chapter_goal");
    assert.equal(result.path[2].content, undefined);
  });
});
