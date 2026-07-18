export type ClientRequestOutcome =
  | "accepted"
  | "confirmed_http_error"
  | "uncertain_network_error";

export function classifyClientRequestFailure(
  status: number | undefined,
): ClientRequestOutcome {
  return status !== undefined && status >= 400 && status < 500
    ? "confirmed_http_error"
    : "uncertain_network_error";
}

export class StableClientRequestIds {
  private readonly values = new Map<string, string>();

  constructor(private readonly createId: () => string = () => crypto.randomUUID()) {}

  get(actionKey: string): string {
    const existing = this.values.get(actionKey);
    if (existing) return existing;

    const created = this.createId();
    this.values.set(actionKey, created);
    return created;
  }

  release(actionKey: string): void {
    this.values.delete(actionKey);
  }

  settle(actionKey: string, outcome: ClientRequestOutcome): void {
    if (outcome !== "uncertain_network_error") this.release(actionKey);
  }
}
