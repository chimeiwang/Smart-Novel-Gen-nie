export type ChapterDraftSnapshot = {
  title: string;
  content: string;
};

export type PendingChapterDraft = {
  snapshot: ChapterDraftSnapshot;
  expectedUpdatedAt: string;
};

export type ChapterSaveState =
  | "saved"
  | "waiting"
  | "saving"
  | "failed"
  | "conflict";

export type ChapterDraftStorage = {
  load: () => PendingChapterDraft | null;
  save: (draft: PendingChapterDraft) => void;
  clear: () => boolean | void;
};

type BrowserStorage = {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
  removeItem: (key: string) => void;
};

type BrowserStorageOwner = {
  readonly localStorage: BrowserStorage;
};

type SaveChapterDraft = (
  request: ChapterDraftSnapshot & { expectedUpdatedAt: string },
) => Promise<{ updatedAt: string }>;

type ChapterSaveCoordinatorOptions = {
  initialSnapshot: ChapterDraftSnapshot;
  initialUpdatedAt: string;
  delayMs: number;
  save: SaveChapterDraft;
  storage?: ChapterDraftStorage;
  onStateChange?: (state: ChapterSaveState) => void;
};

function cloneSnapshot(snapshot: ChapterDraftSnapshot): ChapterDraftSnapshot {
  return { ...snapshot };
}

function snapshotsEqual(
  left: ChapterDraftSnapshot,
  right: ChapterDraftSnapshot,
): boolean {
  return left.title === right.title && left.content === right.content;
}

function isVersionConflict(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "status" in error &&
    error.status === 409
  );
}

function isPendingChapterDraft(value: unknown): value is PendingChapterDraft {
  if (typeof value !== "object" || value === null) return false;
  if (!("snapshot" in value) || !("expectedUpdatedAt" in value)) return false;
  const snapshot = value.snapshot;
  return (
    typeof value.expectedUpdatedAt === "string" &&
    typeof snapshot === "object" &&
    snapshot !== null &&
    "title" in snapshot &&
    typeof snapshot.title === "string" &&
    "content" in snapshot &&
    typeof snapshot.content === "string"
  );
}

export function createChapterDraftStorage(
  storage: BrowserStorage,
  key: string,
): ChapterDraftStorage {
  return {
    load() {
      let raw: string | null;
      try {
        raw = storage.getItem(key);
      } catch {
        return null;
      }
      if (!raw) return null;
      try {
        const value: unknown = JSON.parse(raw);
        if (isPendingChapterDraft(value)) return value;
      } catch {
        // 损坏草稿不能影响编辑器加载，清理后继续使用服务端版本。
      }
      try {
        storage.removeItem(key);
      } catch {
        // 浏览器存储不可用时继续使用服务端版本，不能阻断编辑器加载。
      }
      return null;
    },
    save(draft) {
      try {
        storage.setItem(key, JSON.stringify(draft));
      } catch {
        // 本地备份是降级保护，失败时不能阻断服务端自动保存。
      }
    },
    clear() {
      try {
        storage.removeItem(key);
        return true;
      } catch {
        // 服务端保存结果不应因浏览器存储清理失败而被误报为失败。
        return false;
      }
    },
  };
}

export function createBestEffortChapterDraftStorage(
  owner: BrowserStorageOwner,
  key: string,
): ChapterDraftStorage | undefined {
  try {
    return createChapterDraftStorage(owner.localStorage, key);
  } catch {
    // 某些浏览器会在读取 localStorage 属性时直接抛错，自动保存仍应继续。
    return undefined;
  }
}

export class ChapterSaveCoordinator {
  readonly #delayMs: number;
  readonly #save: SaveChapterDraft;
  readonly #storage?: ChapterDraftStorage;
  readonly #onStateChange?: (state: ChapterSaveState) => void;

  #savedSnapshot: ChapterDraftSnapshot;
  #latestSnapshot: ChapterDraftSnapshot;
  #updatedAt: string;
  #state: ChapterSaveState = "saved";
  #timer: ReturnType<typeof setTimeout> | null = null;
  #inFlight: Promise<void> | null = null;
  #lastError: unknown = null;
  #disposed = false;

  constructor(options: ChapterSaveCoordinatorOptions) {
    this.#delayMs = options.delayMs;
    this.#save = options.save;
    this.#storage = options.storage;
    this.#onStateChange = options.onStateChange;
    this.#savedSnapshot = cloneSnapshot(options.initialSnapshot);
    this.#latestSnapshot = cloneSnapshot(options.initialSnapshot);
    this.#updatedAt = options.initialUpdatedAt;

    const pendingDraft = this.#storage?.load() ?? null;
    if (pendingDraft) {
      if (snapshotsEqual(pendingDraft.snapshot, options.initialSnapshot)) {
        this.#storage?.clear();
      } else if (pendingDraft.expectedUpdatedAt === options.initialUpdatedAt) {
        this.#latestSnapshot = cloneSnapshot(pendingDraft.snapshot);
        this.#setState("waiting");
        this.#armTimer();
      } else {
        this.#latestSnapshot = cloneSnapshot(pendingDraft.snapshot);
        this.#setState("conflict");
      }
    }
  }

  get state(): ChapterSaveState {
    return this.#state;
  }

  get updatedAt(): string {
    return this.#updatedAt;
  }

  get snapshot(): ChapterDraftSnapshot {
    return cloneSnapshot(this.#latestSnapshot);
  }

  discardLocalDraft(): boolean {
    this.#clearTimer();
    if (this.#storage?.clear() === false) return false;
    this.#latestSnapshot = cloneSnapshot(this.#savedSnapshot);
    this.#lastError = null;
    this.#setState("saved");
    return true;
  }

  advanceVersion(updatedAt: string): void {
    if (
      this.#inFlight ||
      !snapshotsEqual(this.#latestSnapshot, this.#savedSnapshot)
    ) {
      throw new Error("存在尚未完成的章节保存，不能推进版本");
    }
    this.#updatedAt = updatedAt;
  }

  schedule(snapshot: ChapterDraftSnapshot): void {
    if (this.#disposed) return;

    this.#latestSnapshot = cloneSnapshot(snapshot);
    this.#persistLatestDraft();

    if (this.#state === "failed" || this.#state === "conflict") return;

    if (snapshotsEqual(this.#latestSnapshot, this.#savedSnapshot)) {
      this.#clearTimer();
      this.#storage?.clear();
      this.#setState("saved");
      return;
    }

    this.#setState("waiting");
    if (!this.#inFlight) this.#armTimer();
  }

  async flush(): Promise<void> {
    this.#clearTimer();

    if (this.#inFlight) return this.#inFlight;
    if (this.#state === "failed" || this.#state === "conflict") {
      throw this.#lastError ?? new Error("章节草稿尚未保存");
    }
    if (snapshotsEqual(this.#latestSnapshot, this.#savedSnapshot)) {
      this.#storage?.clear();
      this.#setState("saved");
      return;
    }

    const operation = this.#drain();
    this.#inFlight = operation;
    try {
      await operation;
    } finally {
      if (this.#inFlight === operation) this.#inFlight = null;
    }
  }

  async retry(): Promise<void> {
    this.#lastError = null;
    this.#setState("waiting");
    await this.flush();
  }

  async dispose(): Promise<void> {
    this.#clearTimer();
    this.#disposed = true;
    try {
      if (this.#inFlight) {
        await this.#inFlight;
      } else if (!snapshotsEqual(this.#latestSnapshot, this.#savedSnapshot)) {
        const operation = this.#drain();
        this.#inFlight = operation;
        await operation;
      }
    } catch {
      // 离开页面时不能阻塞卸载；待保存草稿已同步保留在本地存储中。
    } finally {
      this.#inFlight = null;
    }
  }

  async #drain(): Promise<void> {
    while (!snapshotsEqual(this.#latestSnapshot, this.#savedSnapshot)) {
      const candidate = cloneSnapshot(this.#latestSnapshot);
      const expectedUpdatedAt = this.#updatedAt;
      this.#setState("saving");

      try {
        const response = await this.#save({ ...candidate, expectedUpdatedAt });
        this.#savedSnapshot = candidate;
        this.#updatedAt = response.updatedAt;
        this.#lastError = null;
      } catch (error) {
        this.#lastError = error;
        this.#persistLatestDraft();
        this.#setState(isVersionConflict(error) ? "conflict" : "failed");
        throw error;
      }

      if (snapshotsEqual(this.#latestSnapshot, this.#savedSnapshot)) {
        this.#storage?.clear();
      } else {
        this.#persistLatestDraft();
        this.#setState("waiting");
      }
    }

    this.#setState("saved");
  }

  #persistLatestDraft(): void {
    if (snapshotsEqual(this.#latestSnapshot, this.#savedSnapshot)) {
      this.#storage?.clear();
      return;
    }
    this.#storage?.save({
      snapshot: cloneSnapshot(this.#latestSnapshot),
      expectedUpdatedAt: this.#updatedAt,
    });
  }

  #armTimer(): void {
    this.#clearTimer();
    this.#timer = setTimeout(() => {
      this.#timer = null;
      void this.flush().catch(() => undefined);
    }, this.#delayMs);
  }

  #clearTimer(): void {
    if (!this.#timer) return;
    clearTimeout(this.#timer);
    this.#timer = null;
  }

  #setState(state: ChapterSaveState): void {
    if (this.#state === state) return;
    this.#state = state;
    if (!this.#disposed) this.#onStateChange?.(state);
  }
}
