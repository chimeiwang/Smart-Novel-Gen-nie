import type { components } from "@inkforge/api-client";

export type WorkspaceGroup = "lore" | "planning" | "resources";

export type WorkspaceGroupData = {
  lore: components["schemas"]["WorkspaceLoreResponse"];
  planning: components["schemas"]["WorkspacePlanningResponse"];
  resources: components["schemas"]["WorkspaceResourcesResponse"];
};

export type WorkspaceGroupLoaders = {
  [Group in WorkspaceGroup]: () => Promise<WorkspaceGroupData[Group]>;
};

export type DeferredGroupState<T> = {
  status: "idle" | "loading" | "success" | "error";
  data?: T;
  error?: string;
};

export type DeferredWorkspaceSnapshot = {
  [Group in WorkspaceGroup]: DeferredGroupState<WorkspaceGroupData[Group]>;
};

const TAB_GROUPS: Record<string, WorkspaceGroup | undefined> = {
  characters: "lore",
  lore: "lore",
  progress: "planning",
  storyProgress: "planning",
  storyBackground: "planning",
  worldSetting: "planning",
  writingBible: "planning",
  outline: "planning",
  references: "resources",
  reference: "resources",
  style: "resources",
};

export function groupForTab(tab: string): WorkspaceGroup | null {
  return TAB_GROUPS[tab] ?? null;
}

export class DeferredWorkspaceLoader {
  private current: DeferredWorkspaceSnapshot = {
    lore: { status: "idle" },
    planning: { status: "idle" },
    resources: { status: "idle" },
  };
  private readonly inFlight = new Map<WorkspaceGroup, Promise<unknown>>();
  private readonly listeners = new Set<() => void>();

  constructor(private readonly loaders: WorkspaceGroupLoaders) {}

  snapshot = (): DeferredWorkspaceSnapshot => this.current;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  async load<Group extends WorkspaceGroup>(
    group: Group,
  ): Promise<WorkspaceGroupData[Group]> {
    const state = this.current[group];
    if (state.status === "success" && state.data) {
      return state.data;
    }
    const existing = this.inFlight.get(group);
    if (existing) {
      return existing as Promise<WorkspaceGroupData[Group]>;
    }

    this.update(group, { ...state, status: "loading", error: undefined });
    const request = this.loaders[group]().then(
      (data) => {
        this.update(group, { status: "success", data });
        return data;
      },
      (error: unknown) => {
        const message = error instanceof Error ? error.message : "延迟数据加载失败";
        this.update(group, { status: "error", error: message });
        throw error;
      },
    ).finally(() => {
      this.inFlight.delete(group);
    });
    this.inFlight.set(group, request);
    return request;
  }

  retry<Group extends WorkspaceGroup>(group: Group): Promise<WorkspaceGroupData[Group]> {
    this.update(group, { status: "idle" });
    return this.load(group);
  }

  refresh<Group extends WorkspaceGroup>(group: Group): Promise<WorkspaceGroupData[Group]> {
    return this.retry(group);
  }

  private update<Group extends WorkspaceGroup>(
    group: Group,
    state: DeferredGroupState<WorkspaceGroupData[Group]>,
  ): void {
    this.current = { ...this.current, [group]: state };
    for (const listener of this.listeners) listener();
  }
}
