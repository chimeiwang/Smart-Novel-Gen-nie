import type { ScriptDocument, ScriptScene } from "./types";

export function nodeIdentity(node: { id?: string | null; tempKey?: string | null }): string {
  return node.id ?? node.tempKey ?? "";
}

export function reconcileScriptNodeIds(document: ScriptDocument, nodeIdMap: Record<string, string>): ScriptDocument {
  const identity = <T extends { id?: string | null; tempKey?: string | null }>(node: T): T => {
    const mapped = node.tempKey ? nodeIdMap[node.tempKey] : undefined;
    return mapped ? { ...node, id: mapped, tempKey: null } : node;
  };
  return { ...document, scenes: (document.scenes ?? []).map((scene) => ({ ...identity(scene), lines: (scene.lines ?? []).map(identity) })), dependencies: (document.dependencies ?? []).map((dependency) => ({ ...dependency, consumerSceneId: nodeIdMap[dependency.consumerSceneId] ?? dependency.consumerSceneId, consumerLineId: dependency.consumerLineId ? nodeIdMap[dependency.consumerLineId] ?? dependency.consumerLineId : null })) };
}

export function duplicateScene(scene: ScriptScene, requestId: () => string): ScriptScene {
  return { ...structuredClone(scene), id: null, tempKey: requestId(), title: `${scene.title}（副本）`, lines: (scene.lines ?? []).map((line) => ({ ...structuredClone(line), id: null, tempKey: requestId() })) };
}

export function removeScene(document: ScriptDocument, key: string): ScriptDocument {
  return { ...document, scenes: (document.scenes ?? []).filter((scene) => nodeIdentity(scene) !== key), dependencies: (document.dependencies ?? []).filter((dependency) => dependency.consumerSceneId !== key) };
}

export function reorderScene(document: ScriptDocument, key: string, offset: -1 | 1): ScriptDocument {
  const scenes = [...(document.scenes ?? [])];
  const index = scenes.findIndex((scene) => nodeIdentity(scene) === key);
  const target = index + offset;
  if (index < 0 || target < 0 || target >= scenes.length) return document;
  [scenes[index], scenes[target]] = [scenes[target], scenes[index]];
  return { ...document, scenes };
}
