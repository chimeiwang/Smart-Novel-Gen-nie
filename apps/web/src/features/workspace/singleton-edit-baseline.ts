export type SingletonEditBaseline = {
  expectedUpdatedAt: string | null;
  observedUpdatedAt: string | null;
  hasLocalDraft: boolean;
};

export function createSingletonEditBaseline(
  updatedAt: string | null,
): SingletonEditBaseline {
  return {
    expectedUpdatedAt: updatedAt,
    observedUpdatedAt: updatedAt,
    hasLocalDraft: false,
  };
}

export function markSingletonEditDirty(
  state: SingletonEditBaseline,
): SingletonEditBaseline {
  return { ...state, hasLocalDraft: true };
}

export function observeSingletonEditVersion(
  state: SingletonEditBaseline,
  updatedAt: string | null,
): SingletonEditBaseline {
  if (updatedAt === state.observedUpdatedAt) return state;

  return {
    ...state,
    expectedUpdatedAt: state.hasLocalDraft ? state.expectedUpdatedAt : updatedAt,
    observedUpdatedAt: updatedAt,
  };
}

export function advanceSingletonEditBaseline(
  state: SingletonEditBaseline,
  updatedAt: string,
): SingletonEditBaseline {
  return { ...state, expectedUpdatedAt: updatedAt, hasLocalDraft: false };
}

export function resolveSingletonEditValue<T>(
  state: SingletonEditBaseline,
  localValue: T,
  remoteValue: T,
): T {
  return state.hasLocalDraft || state.expectedUpdatedAt !== state.observedUpdatedAt
    ? localValue
    : remoteValue;
}
