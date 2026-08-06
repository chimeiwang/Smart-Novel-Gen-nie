export type VersionedMutationDraft = {
  id?: string;
  updatedAt?: string;
  clientRequestId?: string;
};

export type ChildMutationPlan<
  TOriginal extends VersionedMutationDraft,
  TUpdate extends VersionedMutationDraft,
  TCreate extends VersionedMutationDraft,
> = {
  deletes: TOriginal[];
  updates: TUpdate[];
  creates: TCreate[];
};

const METADATA_FIELDS = new Set(["id", "createdAt", "updatedAt", "clientRequestId"]);

export function sameBusinessFields(
  before: VersionedMutationDraft | undefined,
  after: VersionedMutationDraft,
): boolean {
  if (!before) return false;
  const fields = new Set([...Object.keys(before), ...Object.keys(after)]);
  for (const field of fields) {
    if (METADATA_FIELDS.has(field)) continue;
    if (!Object.is(
      before[field as keyof VersionedMutationDraft],
      after[field as keyof VersionedMutationDraft],
    )) return false;
  }
  return true;
}

export function buildChildMutationPlan<
  TOriginal extends VersionedMutationDraft,
  TDraft extends VersionedMutationDraft,
>(
  original: readonly TOriginal[],
  draft: readonly TDraft[],
): ChildMutationPlan<TOriginal, TDraft, TDraft> {
  const before = new Map(
    original.flatMap((item) => item.id ? [[item.id, item] as const] : []),
  );
  const afterIds = new Set(draft.flatMap((item) => item.id ? [item.id] : []));
  return {
    deletes: original.filter((item) => Boolean(item.id) && !afterIds.has(item.id as string)),
    updates: draft.filter((item) => Boolean(item.id) && !sameBusinessFields(before.get(item.id as string), item)),
    creates: draft.filter((item) => !item.id),
  };
}

export async function executeChildMutationPlan<
  TOriginal extends VersionedMutationDraft,
  TUpdate extends VersionedMutationDraft,
  TCreate extends VersionedMutationDraft,
>(
  plan: ChildMutationPlan<TOriginal, TUpdate, TCreate>,
  handlers: {
    delete: (item: TOriginal) => Promise<void>;
    update: (item: TUpdate) => Promise<void>;
    create: (item: TCreate) => Promise<void>;
  },
): Promise<void> {
  for (const item of plan.deletes) await handlers.delete(item);
  for (const item of plan.updates) await handlers.update(item);
  for (const item of plan.creates) await handlers.create(item);
}
