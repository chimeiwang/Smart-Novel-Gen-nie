type PollQualityCheckOptions<T> = {
  fetchCheck: () => Promise<T>;
  getStatus: (check: T) => string;
  onUpdate?: (check: T) => void;
  isCancelled?: () => boolean;
  wait?: (milliseconds: number) => Promise<void>;
  maxAttempts?: number;
};

const ACTIVE_STATUSES = new Set(["pending", "running"]);

type QualityCheckPollingCandidate = {
  id: string;
  status: string;
};

export function canResetQualityCheck(
  chapterStatus: string,
  checkStatus: string,
): boolean {
  return chapterStatus !== "completed" && checkStatus === "skipped";
}

export function findQualityCheckToResume<T extends QualityCheckPollingCandidate>(
  checks: readonly T[],
  activeCheckId: string | null,
  resumedCheckId: string | null,
): T | null {
  if (activeCheckId !== null) return null;
  const runningCheck = checks.find((check) => check.status === "running") ?? null;
  if (runningCheck?.id === resumedCheckId) return null;
  return runningCheck;
}

export function findRunningQualityCheck<T extends QualityCheckPollingCandidate>(
  checks: readonly T[],
  activeCheckId: string | null,
): T | null {
  if (activeCheckId !== null) return null;
  return checks.find((check) => check.status === "running") ?? null;
}

function defaultWait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export async function pollQualityCheck<T>(
  options: PollQualityCheckOptions<T>,
): Promise<T | null> {
  const maxAttempts = options.maxAttempts ?? 30;
  const wait = options.wait ?? defaultWait;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (options.isCancelled?.()) return null;

    const check = await options.fetchCheck();
    if (options.isCancelled?.()) return null;
    options.onUpdate?.(check);
    if (!ACTIVE_STATUSES.has(options.getStatus(check))) return check;

    if (attempt < maxAttempts - 1) {
      await wait(Math.min(500 * 2 ** attempt, 4_000));
    }
  }

  throw new Error("质量检查轮询超时，请稍后重试");
}
