const DEFAULT_RETRY_DELAYS_MS = [250, 500, 1_000, 2_000] as const;

type MonitorRunStreamOptions<TOutcome> = {
  open: () => Promise<Response>;
  consume: (response: Response) => Promise<boolean>;
  readOutcome: () => Promise<TOutcome>;
  handleOutcome: (outcome: TOutcome) => void;
  shouldClose: (outcome: TOutcome) => boolean;
  signal?: AbortSignal;
  retryDelaysMs?: readonly number[];
  wait?: (delayMs: number, signal?: AbortSignal) => Promise<void>;
};

export async function monitorRunStream<TOutcome>({
  open,
  consume,
  readOutcome,
  handleOutcome,
  shouldClose,
  signal,
  retryDelaysMs = DEFAULT_RETRY_DELAYS_MS,
  wait = waitForRetry,
}: MonitorRunStreamOptions<TOutcome>): Promise<void> {
  if (retryDelaysMs.length === 0 || retryDelaysMs.some((delay) => delay < 0)) {
    throw new Error("写作事件流重连配置无效");
  }
  let retryAttempt = 0;
  while (true) {
    throwIfAborted(signal);
    let receivedEvent = false;
    try {
      receivedEvent = await consume(await open());
    } catch (error) {
      if (isAbortError(error)) throw error;
      if (signal?.aborted) throw abortError();
    }

    try {
      const outcome = await readOutcome();
      handleOutcome(outcome);
      if (shouldClose(outcome)) return;
    } catch (error) {
      if (isAbortError(error)) throw error;
      if (signal?.aborted) throw abortError();
    }

    if (receivedEvent) retryAttempt = 0;
    const delay = retryDelaysMs[
      Math.min(retryAttempt, retryDelaysMs.length - 1)
    ];
    retryAttempt += 1;
    await wait(delay, signal);
  }
}

function throwIfAborted(signal?: AbortSignal): void {
  if (signal?.aborted) throw abortError();
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function abortError(): DOMException {
  return new DOMException("写作事件流已取消", "AbortError");
}

async function waitForRetry(
  delayMs: number,
  signal?: AbortSignal,
): Promise<void> {
  throwIfAborted(signal);
  await new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, delayMs);
    const onAbort = () => {
      window.clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      reject(abortError());
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}
