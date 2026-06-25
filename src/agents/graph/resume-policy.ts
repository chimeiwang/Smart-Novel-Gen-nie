export type ResumeMode = "interrupt_resume" | "snapshot_resume" | "fresh";

export function isExplicitAgentCommand(message: string): boolean {
  return message.trim().startsWith("@");
}

export function getResumeMode(input: {
  hasPendingCheckpoint: boolean;
  hasGraphStateSnapshot: boolean;
  userMessage: string;
}): ResumeMode {
  if (isExplicitAgentCommand(input.userMessage)) {
    return "fresh";
  }
  if (input.hasPendingCheckpoint && !isExplicitAgentCommand(input.userMessage)) {
    return "interrupt_resume";
  }
  if (input.hasGraphStateSnapshot) {
    return "snapshot_resume";
  }
  return "fresh";
}
