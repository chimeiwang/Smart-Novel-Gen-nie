import type {
  EpisodeAudioClipInput,
  EpisodeEditClipInput,
  EpisodeEditVersion,
  EpisodeMixVersion,
  EpisodePostAsset,
  EpisodeShotOmissionInput,
  EpisodeSubtitleCueInput,
  ProductionBaseline,
  ScriptVersion,
  StoryboardVersion,
} from "./types";

export type TakeMediaFact = { id: string; durationMs: number };

export type EpisodeEditDraft = {
  basedOnVersionId: string | null;
  expectedHeadRevision: number;
  clips: EpisodeEditClipInput[];
  omissions: EpisodeShotOmissionInput[];
};

export type EpisodeMixDraft = {
  basedOnVersionId: string | null;
  expectedHeadRevision: number;
  editVersionId: string;
  audioClips: EpisodeAudioClipInput[];
  subtitleCues: EpisodeSubtitleCueInput[];
};

export function editDraftFromVersion(
  version: EpisodeEditVersion,
  createKey: () => string,
): EpisodeEditDraft {
  return {
    basedOnVersionId: version.id,
    expectedHeadRevision: version.headRevision,
    clips: version.clips.map((clip) => ({
      tempKey: createKey(),
      adoptionId: clip.adoptionId,
      takeId: clip.takeId,
      sourceInMs: clip.sourceInMs,
      sourceOutMs: clip.sourceOutMs,
      sourceAudioMode: clip.sourceAudioMode,
      transitionAfter: clip.transitionAfter,
      transitionDurationMs: clip.transitionDurationMs,
    })),
    omissions: version.omissions.map(({ shotVersionId, reason }) => ({ shotVersionId, reason })),
  };
}

export function editDraftProblems(
  baseline: ProductionBaseline,
  draft: EpisodeEditDraft,
  takeById: Readonly<Record<string, TakeMediaFact>>,
  adoptionTakeIds: Readonly<Record<string, string>> = {},
): string[] {
  const problems: string[] = [];
  if (!draft.clips.length) problems.push("粗剪至少需要一个真实素材片段");
  if (new Set(draft.clips.map((clip) => clip.tempKey)).size !== draft.clips.length) problems.push("片段临时身份重复");
  const shotByAdoption = new Map(baseline.shots.flatMap((shot) => shot.adoptionId ? [[shot.adoptionId, shot] as const] : []));
  for (const [index, clip] of draft.clips.entries()) {
    const shot = shotByAdoption.get(clip.adoptionId);
    const take = takeById[clip.takeId];
    if (!shot || !take || adoptionTakeIds[clip.adoptionId] !== clip.takeId || take.id !== clip.takeId) problems.push(`片段 ${index + 1} 没有匹配本基线的采用素材`);
    if (clip.sourceOutMs - clip.sourceInMs < 500) problems.push(`片段 ${index + 1} 少于 0.5 秒`);
    if (take && clip.sourceOutMs > take.durationMs) problems.push(`片段 ${index + 1} 出点超过实测素材时长`);
    if (clip.transitionAfter === "cut" && clip.transitionDurationMs !== 0) problems.push(`片段 ${index + 1} 的硬切不能设置转场时长`);
    if (clip.transitionAfter === "fade_black" && (clip.transitionDurationMs <= 0 || clip.transitionDurationMs * 2 > clip.sourceOutMs - clip.sourceInMs)) problems.push(`片段 ${index + 1} 的淡黑时长无效`);
  }
  const omitted = new Map(draft.omissions.map((item) => [item.shotVersionId, item.reason.trim()]));
  for (const shot of baseline.shots) {
    const hasClip = draft.clips.some((clip) => clip.adoptionId === shot.adoptionId && Boolean(shot.adoptionId));
    const omission = omitted.get(shot.shotVersionId);
    if (hasClip && omission) problems.push(`镜头 ${shot.ordinal} 不能同时进入粗剪和省略清单`);
    if (!hasClip && !omission) problems.push(`镜头 ${shot.ordinal} 尚未放入粗剪，也没有填写省略原因`);
  }
  return [...new Set(problems)];
}

export function mixDraftFromVersion(version: EpisodeMixVersion): EpisodeMixDraft {
  return {
    basedOnVersionId: version.id,
    expectedHeadRevision: version.headRevision,
    editVersionId: version.editVersionId,
    audioClips: version.audioClips.map(({ trackKind, assetId, shotVersionId, timelineStartMs, sourceInMs, sourceOutMs, gainMillibels, fadeInMs, fadeOutMs }) => ({ trackKind, assetId, shotVersionId, timelineStartMs, sourceInMs, sourceOutMs, gainMillibels, fadeInMs, fadeOutMs })),
    subtitleCues: version.subtitleCues.map(({ shotVersionId, scriptLineId, startMs, endMs, speaker, text }) => ({ shotVersionId, scriptLineId, startMs, endMs, speaker, text })),
  };
}

export function mixDraftProblems(
  edit: EpisodeEditVersion,
  draft: EpisodeMixDraft,
  audioAssets: EpisodePostAsset[],
  storyboard: StoryboardVersion,
  script: ScriptVersion,
): string[] {
  const problems: string[] = [];
  if (draft.editVersionId !== edit.id) problems.push("声音版本没有绑定当前选择的粗剪版本");
  const assets = new Map(audioAssets.map((asset) => [asset.id, asset]));
  const shotVersions = new Map(storyboard.shots.map((shot) => [shot.id, shot]));
  const lineIds = new Set((script.document.scenes ?? []).flatMap((scene) => scene.lines?.flatMap((line) => line.id ? [line.id] : []) ?? []));
  draft.audioClips.forEach((clip, index) => {
    const asset = assets.get(clip.assetId);
    if (!asset || asset.modality !== "audio") problems.push(`音轨 ${index + 1} 的素材不可用`);
    if (clip.sourceOutMs <= clip.sourceInMs || (asset && clip.sourceOutMs > asset.durationMs)) problems.push(`音轨 ${index + 1} 的素材区间无效`);
    if (clip.fadeInMs + clip.fadeOutMs > clip.sourceOutMs - clip.sourceInMs) problems.push(`音轨 ${index + 1} 的淡入淡出超过片段时长`);
    if (clip.timelineStartMs + clip.sourceOutMs - clip.sourceInMs > edit.totalDurationMs) problems.push(`音轨 ${index + 1} 超出粗剪总时长`);
    if (clip.shotVersionId && !shotVersions.has(clip.shotVersionId)) problems.push(`音轨 ${index + 1} 绑定了其他制作基线的镜头`);
  });
  draft.subtitleCues.forEach((cue, index) => {
    const shot = shotVersions.get(cue.shotVersionId);
    if (!shot || !lineIds.has(cue.scriptLineId) || !shot.scriptLineIds.includes(cue.scriptLineId)) problems.push(`字幕 ${index + 1} 没有绑定该镜头的正式剧本节点`);
    if (cue.endMs <= cue.startMs || cue.endMs > edit.totalDurationMs) problems.push(`字幕 ${index + 1} 的时间范围无效`);
    if (!cue.text.trim()) problems.push(`字幕 ${index + 1} 没有文案`);
  });
  return [...new Set(problems)];
}
