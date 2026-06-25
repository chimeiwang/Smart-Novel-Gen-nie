export type OptimisticWritingMessagePersistenceInput = {
  persist?: boolean;
  role?: "user" | "agent" | "system";
  content?: string;
};

export function shouldPersistOptimisticWritingMessage(
  input: OptimisticWritingMessagePersistenceInput
): boolean {
  return input.persist !== false;
}
