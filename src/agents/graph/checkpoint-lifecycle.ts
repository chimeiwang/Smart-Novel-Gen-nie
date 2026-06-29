type TimerHandle = ReturnType<typeof setTimeout>;

export type CheckpointCleanupTimerApi = {
  setTimeout: (callback: () => void, delayMs: number) => TimerHandle;
  clearTimeout: (handle: TimerHandle) => void;
};

export type ScheduleCheckpointCleanupInput = {
  threadId: string;
  ttlMs: number;
  cleanup: (threadId: string) => Promise<void>;
  onError?: (error: unknown, threadId: string) => void;
};

const defaultTimerApi: CheckpointCleanupTimerApi = {
  setTimeout: (callback, delayMs) => setTimeout(callback, delayMs),
  clearTimeout: (handle) => clearTimeout(handle),
};

/**
 * 为进程内 checkpoint 提供可取消的 TTL。
 *
 * MemorySaver 本身不会淘汰旧 thread；该调度器只管理定时器，实际删除由调用方注入，
 * 便于保持 MemorySaver 单例仍由 graph-definition.ts 持有。
 */
export class CheckpointCleanupScheduler {
  private readonly timers = new Map<string, TimerHandle>();

  constructor(private readonly timerApi: CheckpointCleanupTimerApi = defaultTimerApi) {}

  schedule(input: ScheduleCheckpointCleanupInput): void {
    this.cancel(input.threadId);
    if (!Number.isFinite(input.ttlMs) || input.ttlMs <= 0) return;

    const handle = this.timerApi.setTimeout(() => {
      this.timers.delete(input.threadId);
      void input.cleanup(input.threadId).catch((error) => {
        input.onError?.(error, input.threadId);
      });
    }, input.ttlMs);
    handle.unref?.();
    this.timers.set(input.threadId, handle);
  }

  cancel(threadId: string): boolean {
    const handle = this.timers.get(threadId);
    if (!handle) return false;
    this.timerApi.clearTimeout(handle);
    this.timers.delete(threadId);
    return true;
  }

  has(threadId: string): boolean {
    return this.timers.has(threadId);
  }
}
