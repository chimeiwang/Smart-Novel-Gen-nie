export type ScriptSaveState = "saved" | "waiting" | "saving" | "failed" | "conflict";

export type DraftSnapshot<T> = { document: T; revision: number };
export type DraftWrite<T> = DraftSnapshot<T> & { clientRequestId: string };
export type DraftAcknowledgement<T> = DraftSnapshot<T> & {
  /** 服务端分配节点身份后，仅映射身份，不覆盖保存期间继续输入的文本。 */
  reconcileLocal?: (latest: T) => T;
};

export type PendingScriptDraft<T> = {
  latest: T;
  baseline: DraftSnapshot<T>;
  pending: DraftWrite<T> | null;
};

type Options<T> = {
  initial: DraftSnapshot<T>;
  delayMs?: number;
  /** 保留现有剧本默认文案，同时允许分镜复用同一套并发与恢复语义。 */
  resourceLabel?: string;
  requestId: () => string;
  save: (request: DraftWrite<T>) => Promise<DraftAcknowledgement<T>>;
  onChange?: () => void;
  persist?: (draft: PendingScriptDraft<T> | null) => void;
  restored?: PendingScriptDraft<T> | null;
};

const copy = <T,>(value: T): T => structuredClone(value);
const same = (left: unknown, right: unknown) => JSON.stringify(left) === JSON.stringify(right);
const conflict = (error: unknown) => typeof error === "object" && error !== null && "status" in error && error.status === 409;

/** 一个实例只属于一集。保存、采用和确认共用串行屏障，迟到响应不能写入另一集。 */
export class ScriptDraftCoordinator<T> {
  readonly #options: Options<T>;
  #baseline: DraftSnapshot<T>;
  #latest: T;
  #pending: DraftWrite<T> | null = null;
  #state: ScriptSaveState = "saved";
  #error: unknown = null;
  #timer: ReturnType<typeof setTimeout> | null = null;
  #flight: Promise<void> | null = null;
  #exclusive = false;
  #disposed = false;

  constructor(options: Options<T>) {
    this.#options = options;
    this.#baseline = copy(options.initial);
    this.#latest = copy(options.initial.document);
    if (options.restored) {
      this.#latest = copy(options.restored.latest);
      this.#pending = copy(options.restored.pending);
      if (options.restored.baseline.revision !== options.initial.revision) {
        // 有未知写入时仍保留原幂等请求；不能拿新 revision 重发成另一条命令。
        this.#state = this.#pending ? "failed" : "conflict";
      } else if (!same(this.#latest, this.#baseline.document) || this.#pending) {
        this.#state = this.#pending ? "failed" : "waiting";
      }
    }
  }

  get document(): T { return copy(this.#latest); }
  get revision(): number { return this.#baseline.revision; }
  get state(): ScriptSaveState { return this.#state; }
  get busy(): boolean { return this.#exclusive || this.#flight !== null; }
  get commandBusy(): boolean { return this.#exclusive; }
  get dirty(): boolean { return this.#pending !== null || !same(this.#latest, this.#baseline.document); }
  get error(): unknown { return this.#error; }

  schedule(document: T): void {
    if (this.#disposed || this.#exclusive) throw new Error(`${this.#options.resourceLabel ?? "剧本"}正在执行确认或采用，请稍后编辑`);
    this.#latest = copy(document);
    this.#persist();
    if (this.#state === "failed" || this.#state === "conflict") { this.#notify(); return; }
    this.#state = this.dirty ? "waiting" : "saved";
    this.#clearTimer();
    if (this.dirty && !this.#flight) {
      this.#timer = setTimeout(() => { void this.flush().catch(() => undefined); }, this.#options.delayMs ?? 1200);
    }
    this.#notify();
  }

  async flush(): Promise<void> {
    this.#clearTimer();
    if (this.#flight) return this.#flight;
    if (this.#state === "failed" || this.#state === "conflict") throw this.#error ?? new Error(`${this.#options.resourceLabel ?? "剧本"}工作稿尚未保存，请先处理保存状态`);
    const operation = this.#drain();
    this.#flight = operation;
    try { await operation; } finally { if (this.#flight === operation) this.#flight = null; this.#notify(); }
  }

  async retry(): Promise<void> {
    if (this.#state === "conflict") throw new Error("工作稿有冲突，请先比较远端版本");
    this.#error = null;
    this.#state = "waiting";
    // #pending 保持原请求 ID、内容与 revision，save 适配器先查询命令回执。
    await this.flush();
  }

  async runExclusive<R>(command: (snapshot: DraftSnapshot<T>) => Promise<{ result: R; draft?: DraftSnapshot<T> }>): Promise<R> {
    if (this.#disposed || this.#exclusive) throw new Error(`已有${this.#options.resourceLabel ?? "剧本"}命令正在处理`);
    this.#exclusive = true;
    this.#notify();
    try {
      await this.flush();
      const reply = await command(copy(this.#baseline));
      if (reply.draft) {
        this.#baseline = copy(reply.draft);
        this.#latest = copy(reply.draft.document);
        this.#state = "saved";
        this.#persist();
      }
      return reply.result;
    } finally { this.#exclusive = false; this.#notify(); }
  }

  /** 只有作者比较后明确选择，才用最新 revision 继续保存本地内容。 */
  resolveConflict(remote: DraftSnapshot<T>, keepLocal: boolean): void {
    if (this.busy) throw new Error("保存尚未完成");
    this.#baseline = copy(remote);
    if (!keepLocal) this.#latest = copy(remote.document);
    this.#pending = null;
    this.#error = null;
    this.#state = this.dirty ? "waiting" : "saved";
    this.#persist();
    this.#clearTimer();
    if (this.dirty && !this.#disposed) {
      this.#timer = setTimeout(() => { void this.flush().catch(() => undefined); }, this.#options.delayMs ?? 1200);
    }
    this.#notify();
  }

  dispose(): void { this.#disposed = true; this.#clearTimer(); }
  activate(): void {
    this.#disposed = false;
    if (this.#state === "waiting" && this.dirty && !this.#flight) this.#timer = setTimeout(() => { void this.flush().catch(() => undefined); }, this.#options.delayMs ?? 1200);
  }

  async #drain(): Promise<void> {
    while (this.dirty) {
      this.#pending ??= { document: copy(this.#latest), revision: this.#baseline.revision, clientRequestId: this.#options.requestId() };
      const request = copy(this.#pending);
      this.#state = "saving";
      this.#persist();
      this.#notify();
      try {
        const response = await this.#options.save(request);
        if (response.revision < this.#baseline.revision) throw Object.assign(new Error("原命令已完成，但远端工作稿已有更新，请比较后继续"), { status: 409 });
        const unchanged = same(this.#latest, request.document);
        this.#baseline = { document: copy(response.document), revision: response.revision };
        this.#latest = unchanged ? copy(response.document) : response.reconcileLocal ? response.reconcileLocal(copy(this.#latest)) : this.#latest;
        this.#pending = null;
        this.#state = this.dirty ? "waiting" : "saved";
        this.#error = null;
        this.#persist();
        this.#notify();
        if (this.#disposed) return;
      } catch (error) {
        this.#error = error;
        this.#state = conflict(error) ? "conflict" : "failed";
        if (typeof error === "object" && error !== null && "status" in error && typeof error.status === "number" && error.status >= 400 && error.status < 500 && error.status !== 409) this.#pending = null;
        this.#persist();
        this.#notify();
        throw error;
      }
    }
  }

  #clearTimer(): void { if (this.#timer) clearTimeout(this.#timer); this.#timer = null; }
  #notify(): void { if (!this.#disposed) this.#options.onChange?.(); }
  #persist(): void {
    try { this.#options.persist?.(this.dirty ? { latest: copy(this.#latest), baseline: copy(this.#baseline), pending: copy(this.#pending) } : null); }
    catch { /* 浏览器备份不可用不阻止权威保存；状态仍以 Core 回包为准。 */ }
  }
}
