type SaveRegistration = { novelId: string; episodeId: string; flush: () => Promise<void>; pending: () => boolean };
const registrations = new Set<SaveRegistration>();

export function registerEpisodeSave(registration: SaveRegistration): () => void {
  registrations.add(registration);
  return () => { registrations.delete(registration); };
}

export async function flushEpisodeSaves(novelId: string, exceptEpisodeId?: string): Promise<void> {
  for (const registration of registrations) if (registration.novelId === novelId && registration.episodeId !== exceptEpisodeId) await registration.flush();
}

export function hasPendingEpisodeSave(novelId: string): boolean {
  return [...registrations].some((registration) => registration.novelId === novelId && registration.pending());
}
