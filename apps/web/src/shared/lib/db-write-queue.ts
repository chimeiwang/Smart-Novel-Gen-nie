import { logger } from "./logger";

export type DbWriteQueueTask = () => Promise<void>;

export interface DbWriteQueueStats {
  enqueued: number;
  completed: number;
  failed: number;
  dropped: number;
  active: number;
  queued: number;
}

export interface DbWriteQueueOptions {
  maxSize?: number;
  concurrency?: number;
  onDrop?: (label: string, stats: DbWriteQueueStats) => void;
  onError?: (error: unknown, label: string, stats: DbWriteQueueStats) => void;
}

interface QueuedDbWrite {
  label: string;
  task: DbWriteQueueTask;
}

const DEFAULT_MAX_SIZE = 100;
const DEFAULT_CONCURRENCY = 3;

export class BoundedDbWriteQueue {
  private readonly maxSize: number;
  private readonly concurrency: number;
  private readonly onDrop?: DbWriteQueueOptions["onDrop"];
  private readonly onError?: DbWriteQueueOptions["onError"];
  private readonly queue: QueuedDbWrite[] = [];
  private readonly idleResolvers = new Set<() => void>();
  private active = 0;
  private enqueued = 0;
  private completed = 0;
  private failed = 0;
  private dropped = 0;

  constructor(options: DbWriteQueueOptions = {}) {
    this.maxSize = Math.max(1, options.maxSize ?? DEFAULT_MAX_SIZE);
    this.concurrency = Math.max(1, options.concurrency ?? DEFAULT_CONCURRENCY);
    this.onDrop = options.onDrop;
    this.onError = options.onError;
  }

  enqueue(task: DbWriteQueueTask, label = "db-write"): boolean {
    if (this.active + this.queue.length >= this.maxSize) {
      this.dropped += 1;
      this.onDrop?.(label, this.getStats());
      return false;
    }

    this.enqueued += 1;
    this.queue.push({ label, task });
    this.drain();
    return true;
  }

  getStats(): DbWriteQueueStats {
    return {
      enqueued: this.enqueued,
      completed: this.completed,
      failed: this.failed,
      dropped: this.dropped,
      active: this.active,
      queued: this.queue.length,
    };
  }

  onIdle(): Promise<void> {
    if (this.active === 0 && this.queue.length === 0) {
      return Promise.resolve();
    }

    return new Promise((resolve) => {
      this.idleResolvers.add(resolve);
    });
  }

  private drain(): void {
    while (this.active < this.concurrency && this.queue.length > 0) {
      const item = this.queue.shift()!;
      this.active += 1;
      void this.run(item);
    }
  }

  private async run(item: QueuedDbWrite): Promise<void> {
    try {
      await item.task();
      this.completed += 1;
    } catch (error) {
      this.failed += 1;
      this.onError?.(error, item.label, this.getStats());
    } finally {
      this.active -= 1;
      this.resolveIdleIfNeeded();
      this.drain();
    }
  }

  private resolveIdleIfNeeded(): void {
    if (this.active !== 0 || this.queue.length !== 0) return;

    for (const resolve of this.idleResolvers) {
      resolve();
    }
    this.idleResolvers.clear();
  }
}

export const dbWriteQueue = new BoundedDbWriteQueue({
  maxSize: DEFAULT_MAX_SIZE,
  concurrency: DEFAULT_CONCURRENCY,
  onDrop(label, stats) {
    logger.warn("DB_WRITE_QUEUE", "Dropped non-critical DB write because the queue is full", {
      label,
      ...stats,
    });
  },
  onError(error, label, stats) {
    logger.warn("DB_WRITE_QUEUE", "Non-critical DB write failed", {
      label,
      error: error instanceof Error ? error.message : String(error),
      ...stats,
    });
  },
});

export function enqueueDbWrite(task: DbWriteQueueTask, label?: string): boolean {
  return dbWriteQueue.enqueue(task, label);
}

export function getDbWriteQueueStats(): DbWriteQueueStats {
  return dbWriteQueue.getStats();
}

export function waitForDbWriteQueueIdle(): Promise<void> {
  return dbWriteQueue.onIdle();
}
