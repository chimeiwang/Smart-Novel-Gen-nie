/** 持续观察同一任务；状态仍活跃或暂时断网时继续，离开后取消在途请求。 */
export function startTaskPolling(
  poll: (signal: AbortSignal) => Promise<boolean>,
  onError: (error: unknown) => void,
  intervalMs = 1800,
): () => void {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout>;

  const tick = async () => {
    if (controller.signal.aborted) return;
    let active = true;
    try {
      active = await poll(controller.signal);
    } catch (error) {
      if (!controller.signal.aborted) onError(error);
    }
    if (active && !controller.signal.aborted) {
      timer = setTimeout(() => void tick(), intervalMs);
    }
  };

  timer = setTimeout(() => void tick(), intervalMs);
  return () => {
    controller.abort();
    clearTimeout(timer);
  };
}
