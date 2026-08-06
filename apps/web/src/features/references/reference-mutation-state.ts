export type ReferenceMutationState = {
  clientRequestId: string;
};

type RequestIdFactory = () => string;

export function createReferenceMutationState(
  factory: RequestIdFactory = createClientRequestId,
): ReferenceMutationState {
  return { clientRequestId: factory() };
}

export function advanceReferenceCreateIdentity(
  current: ReferenceMutationState,
  succeeded: boolean,
  factory: RequestIdFactory = createClientRequestId,
): ReferenceMutationState {
  return succeeded ? createReferenceMutationState(factory) : current;
}

export function buildReferenceUpdateBody<T extends object>(
  reference: { updatedAt: string },
  changes: T,
): T & { expectedUpdatedAt: string } {
  return { ...changes, expectedUpdatedAt: reference.updatedAt };
}

export function buildReferenceDeleteBody(reference: { updatedAt: string }): {
  expectedUpdatedAt: string;
} {
  return { expectedUpdatedAt: reference.updatedAt };
}
import { createClientRequestId } from "@/lib/api/client-request-id";
