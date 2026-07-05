import { prisma } from "@/shared/db/prisma";

const EXPECTED_ROOT_TITLES = [
  "第一阶段·裂痕（第1-15章）",
  "第二阶段·疑云（第16-40章）",
  "第三阶段·碎片（第41-65章）",
  "第四阶段·抉择（第66-90章）",
] as const;

type Node = {
  id: string;
  parentId: string | null;
  title: string;
  kind: "stage" | "plot_unit" | "chapter_group";
  order: number;
};

async function main() {
  const args = new Set(process.argv.slice(2));
  const apply = args.has("--apply");
  const novelId = readArg("--novel-id");
  const novelName = readArg("--novel-name") ?? "遗产猎人";
  const novels = await prisma.novel.findMany({
    where: novelId ? { id: novelId } : { name: novelName },
    select: {
      id: true,
      name: true,
      outlineNodes: {
        select: { id: true, parentId: true, title: true, kind: true, order: true },
      },
    },
  });
  if (novels.length !== 1) {
    throw new Error(`必须精确匹配一本小说，当前匹配数量：${novels.length}`);
  }
  const novel = novels[0];
  const nodes = novel.outlineNodes as Node[];
  const roots = nodes.filter((node) => node.parentId === null);
  const keptRoots = EXPECTED_ROOT_TITLES.map((title) => roots.find((node) => node.title === title));
  const missingRoots = EXPECTED_ROOT_TITLES.filter((_, index) => !keptRoots[index]);
  if (missingRoots.length) throw new Error(`缺少预期最新阶段：${missingRoots.join("、")}`);

  const childrenByParent = new Map<string, Node[]>();
  for (const node of nodes) {
    if (!node.parentId) continue;
    childrenByParent.set(node.parentId, [...(childrenByParent.get(node.parentId) ?? []), node]);
  }
  const keepIds = new Set<string>();
  const visit = (node: Node) => {
    keepIds.add(node.id);
    for (const child of childrenByParent.get(node.id) ?? []) visit(child);
  };
  for (const root of keptRoots) visit(root!);

  const kept = nodes.filter((node) => keepIds.has(node.id));
  const dirty = nodes.filter((node) => !keepIds.has(node.id));
  const ranges = new Map<string, { start: number; end: number }>();
  for (const node of kept) {
    const range = parseChapterRange(node.title);
    if (!range) throw new Error(`无法从保留节点标题解析章节范围：${node.title}`);
    ranges.set(node.id, range);
  }
  validateTree(kept, ranges);

  const report = {
    novel: { id: novel.id, name: novel.name },
    mode: apply ? "apply" : "dry-run",
    keepCount: kept.length,
    deleteCount: dirty.length,
    keptRoots: keptRoots.map((node) => node!.title),
    deletedRoots: roots.filter((node) => !keepIds.has(node.id)).map((node) => node.title),
  };
  console.log(JSON.stringify(report, null, 2));
  if (!apply) {
    console.log("dry-run 完成；确认无误后增加 --apply 执行清理。");
    return;
  }

  await prisma.$transaction(async (tx) => {
    const depths = computeDepths(nodes);
    const dirtyDepths = [...new Set(dirty.map((node) => depths.get(node.id) ?? 0))].sort((a, b) => b - a);
    for (const depth of dirtyDepths) {
      const ids = dirty.filter((node) => (depths.get(node.id) ?? 0) === depth).map((node) => node.id);
      if (ids.length) await tx.outlineNode.deleteMany({ where: { id: { in: ids }, novelId: novel.id } });
    }
    for (const node of kept) {
      const range = ranges.get(node.id)!;
      await tx.outlineNode.update({
        where: { id: node.id },
        data: { chapterStartOrder: range.start, chapterEndOrder: range.end },
      });
    }
  });

  const remaining = await prisma.outlineNode.findMany({
    where: { novelId: novel.id },
    select: { id: true, chapterStartOrder: true, chapterEndOrder: true },
  });
  if (remaining.length !== kept.length || remaining.some((node) => node.chapterStartOrder == null || node.chapterEndOrder == null)) {
    throw new Error("清理后的大纲树验收失败");
  }
  console.log(`清理完成：保留 ${remaining.length} 个节点，删除 ${dirty.length} 个旧节点。`);
}

function readArg(name: string): string | undefined {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

function parseChapterRange(title: string): { start: number; end: number } | null {
  const match = title.match(/第\s*(\d+)\s*(?:章\s*)?[-—~～至到]\s*(\d+)\s*章/);
  if (!match) return null;
  const start = Number(match[1]);
  const end = Number(match[2]);
  return Number.isInteger(start) && Number.isInteger(end) && start > 0 && end >= start ? { start, end } : null;
}

function validateTree(nodes: Node[], ranges: Map<string, { start: number; end: number }>) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const siblings = new Map<string, Node[]>();
  for (const node of nodes) {
    const parentKey = node.parentId ?? "__root__";
    siblings.set(parentKey, [...(siblings.get(parentKey) ?? []), node]);
    if (!node.parentId) {
      if (node.kind !== "stage") throw new Error(`顶层节点不是 stage：${node.title}`);
      continue;
    }
    const parent = byId.get(node.parentId);
    if (!parent) throw new Error(`保留节点缺少父节点：${node.title}`);
    if (node.kind === "plot_unit" && parent.kind !== "stage") throw new Error(`plot_unit 父节点类型错误：${node.title}`);
    if (node.kind === "chapter_group" && parent.kind !== "plot_unit") throw new Error(`chapter_group 父节点类型错误：${node.title}`);
    const range = ranges.get(node.id)!;
    const parentRange = ranges.get(parent.id)!;
    if (range.start < parentRange.start || range.end > parentRange.end) {
      throw new Error(`节点章节范围超出父节点：${node.title}`);
    }
  }
  for (const group of siblings.values()) {
    const sorted = [...group].sort((a, b) => ranges.get(a.id)!.start - ranges.get(b.id)!.start);
    for (let index = 1; index < sorted.length; index += 1) {
      if (ranges.get(sorted[index].id)!.start <= ranges.get(sorted[index - 1].id)!.end) {
        throw new Error(`同级章节范围重叠：${sorted[index - 1].title} 与 ${sorted[index].title}`);
      }
    }
  }
}

function computeDepths(nodes: Node[]): Map<string, number> {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const depths = new Map<string, number>();
  const depthOf = (node: Node): number => {
    const cached = depths.get(node.id);
    if (cached !== undefined) return cached;
    const depth = node.parentId && byId.has(node.parentId) ? depthOf(byId.get(node.parentId)!) + 1 : 0;
    depths.set(node.id, depth);
    return depth;
  };
  for (const node of nodes) depthOf(node);
  return depths;
}

main()
  .catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  })
  .finally(async () => prisma.$disconnect());
