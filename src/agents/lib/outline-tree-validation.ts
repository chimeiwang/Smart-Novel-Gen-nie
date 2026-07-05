import type { AgentUpdates } from "@/shared/contracts/agent-updates";

type Adjustment = NonNullable<AgentUpdates["outlineAdjustments"]>[number];

export function validateOutlineReplacement(adjustments: Adjustment[] | undefined): string[] {
  if (!adjustments?.length) return ["replace 模式必须提供完整 outlineAdjustments"];
  const errors: string[] = [];
  const creates = adjustments.filter((item) => item.action === "create");
  if (creates.length !== adjustments.length) {
    errors.push("replace 模式只允许 create adjustment；旧树由服务端统一删除");
  }

  const byKey = new Map<string, Adjustment>();
  for (const node of creates) {
    const label = node.title || node.nodeTitle || node.clientKey || "未命名节点";
    if (!node.clientKey?.trim()) {
      errors.push(`replace 节点 ${label} 必须提供 clientKey`);
      continue;
    }
    if (byKey.has(node.clientKey)) {
      errors.push(`replace 大纲存在重复 clientKey=${node.clientKey}`);
    } else {
      byKey.set(node.clientKey, node);
    }
    if (!node.kind) errors.push(`replace 节点 ${label} 缺少 kind`);
    if (!node.chapterStartOrder || !node.chapterEndOrder) {
      errors.push(`replace 节点 ${label} 缺少完整章节范围`);
    } else if (node.chapterStartOrder > node.chapterEndOrder) {
      errors.push(`replace 节点 ${label} 的结束章节小于起始章节`);
    }
  }

  for (const node of creates) {
    const label = node.title || node.nodeTitle || node.clientKey || "未命名节点";
    if (node.kind === "stage") {
      if (node.parentId || node.parentKey) errors.push(`stage ${label} 必须是顶层节点`);
      continue;
    }
    if (node.parentId) errors.push(`replace 节点 ${label} 不能引用旧树 parentId`);
    if (!node.parentKey) {
      errors.push(`${node.kind ?? "大纲"} ${label} 必须通过 parentKey 引用本次整树父节点`);
      continue;
    }
    const parent = byKey.get(node.parentKey);
    if (!parent) {
      errors.push(`replace 节点 ${label} 找不到 parentKey=${node.parentKey}`);
      continue;
    }
    if (node.kind === "plot_unit" && parent.kind !== "stage") {
      errors.push(`plot_unit ${label} 的父节点必须是 stage`);
    }
    if (node.kind === "chapter_group" && parent.kind !== "plot_unit") {
      errors.push(`chapter_group ${label} 的父节点必须是 plot_unit`);
    }
    if (
      node.chapterStartOrder && node.chapterEndOrder &&
      parent.chapterStartOrder && parent.chapterEndOrder &&
      (node.chapterStartOrder < parent.chapterStartOrder || node.chapterEndOrder > parent.chapterEndOrder)
    ) {
      errors.push(`节点 ${label} 的章节范围超出父节点 ${parent.title || parent.nodeTitle || parent.clientKey}`);
    }
  }

  const siblings = new Map<string, Adjustment[]>();
  for (const node of creates) {
    const parentKey = node.parentKey ?? "__root__";
    siblings.set(parentKey, [...(siblings.get(parentKey) ?? []), node]);
  }
  for (const nodes of siblings.values()) {
    const sorted = nodes
      .filter((node) => node.chapterStartOrder && node.chapterEndOrder)
      .sort((a, b) => a.chapterStartOrder! - b.chapterStartOrder!);
    for (let index = 1; index < sorted.length; index += 1) {
      if (sorted[index].chapterStartOrder! <= sorted[index - 1].chapterEndOrder!) {
        errors.push(`同级节点章节范围重叠：${sorted[index - 1].title} 与 ${sorted[index].title}`);
      }
    }
  }

  return [...new Set(errors)];
}
