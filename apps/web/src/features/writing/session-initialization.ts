type SessionWithId = {
  id: string;
};

type WritingSessionInitializationOptions<TSession extends SessionWithId> = {
  sessions: readonly TSession[];
  alreadyInitialized: boolean;
  selectDefaultSessionId: (sessions: readonly TSession[]) => string | null;
  resetSessionContext: (sessionId: string | null) => void;
  loadSessionMessages: (sessionId: string) => Promise<void>;
  loadReviewArtifacts: (sessions: readonly TSession[]) => Promise<void>;
};

export async function coordinateWritingSessionInitialization<
  TSession extends SessionWithId,
>({
  sessions,
  alreadyInitialized,
  selectDefaultSessionId,
  resetSessionContext,
  loadSessionMessages,
  loadReviewArtifacts,
}: WritingSessionInitializationOptions<TSession>): Promise<void> {
  if (alreadyInitialized) {
    await loadReviewArtifacts(sessions);
    return;
  }

  const defaultSessionId = selectDefaultSessionId(sessions);
  resetSessionContext(defaultSessionId);
  await Promise.all([
    defaultSessionId ? loadSessionMessages(defaultSessionId) : Promise.resolve(),
    loadReviewArtifacts(sessions),
  ]);
}
