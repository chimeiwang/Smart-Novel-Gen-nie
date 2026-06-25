export function validateResumeSessionBinding(input: {
  requestedWritingSessionId?: string | null;
  taskWritingSessionId?: string | null;
}): string | null {
  if (!input.requestedWritingSessionId) return null;
  if (input.taskWritingSessionId === input.requestedWritingSessionId) return null;
  return "当前任务不属于所选写作会话";
}
