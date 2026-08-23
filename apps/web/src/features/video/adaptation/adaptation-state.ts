import type {
  AdaptationCandidate,
  CandidateBeat,
  CandidateShot,
  FormalPlan,
  FormalShot,
  SourceRange,
} from "./types";

export type DiscardedShot = {
  shot: CandidateShot;
  beatKey: string;
  sceneIndex: number;
  beatIndex: number;
  shotIndex: number;
};

export type SourceSegment = {
  start: number;
  end: number;
  text: string;
  shotKeys: string[];
};

export function cloneCandidate(plan: AdaptationCandidate): AdaptationCandidate {
  return {
    ...plan,
    suggestedEpisodeBreakAfterShotKeys: [...(plan.suggestedEpisodeBreakAfterShotKeys ?? [])],
    scenes: plan.scenes.map((scene) => ({
      ...scene,
      beats: scene.beats.map((beat) => ({
        ...beat,
        sourceRanges: beat.sourceRanges.map((range) => ({ ...range })),
        shots: beat.shots.map((shot) => ({
          ...shot,
          sourceRanges: shot.sourceRanges.map((range) => ({ ...range })),
        })),
      })),
    })),
  };
}

export function flattenCandidateShots(plan: AdaptationCandidate): CandidateShot[] {
  return plan.scenes.flatMap((scene) => scene.beats.flatMap((beat) => beat.shots));
}

export function flattenFormalShots(plan: FormalPlan): FormalShot[] {
  return plan.scenes.flatMap((scene) => scene.beats.flatMap((beat) => beat.shots));
}

export function renumberCandidate(plan: AdaptationCandidate): AdaptationCandidate {
  const shotKeyMap = new Map<string, string>();
  let beatNumber = 0;
  let shotNumber = 0;
  const scenes = plan.scenes.map((scene, sceneIndex) => ({
    ...scene,
    sceneKey: key("SC", sceneIndex + 1),
    beats: scene.beats.map((beat) => {
      beatNumber += 1;
      return {
        ...beat,
        beatKey: key("B", beatNumber),
        shots: beat.shots.map((shot) => {
          shotNumber += 1;
          const shotKey = key("S", shotNumber);
          shotKeyMap.set(shot.shotKey, shotKey);
          return { ...shot, shotKey };
        }),
      };
    }),
  }));
  const lastShotKey = key("S", shotNumber);
  return {
    ...plan,
    scenes,
    suggestedEpisodeBreakAfterShotKeys: (plan.suggestedEpisodeBreakAfterShotKeys ?? [])
      .map((shotKey) => shotKeyMap.get(shotKey))
      .filter((shotKey): shotKey is string => Boolean(shotKey) && shotKey !== lastShotKey),
  };
}

export function updateCandidateShot(
  plan: AdaptationCandidate,
  shotKey: string,
  patch: Partial<Omit<CandidateShot, "shotKey" | "sourceRanges">>,
): AdaptationCandidate {
  return {
    ...plan,
    scenes: plan.scenes.map((scene) => ({
      ...scene,
      beats: scene.beats.map((beat) => ({
        ...beat,
        shots: beat.shots.map((shot) => {
          if (shot.shotKey !== shotKey) return shot;
          if (patch.adaptationType === "supplemental") {
            return { ...shot, ...patch, sourceRanges: [] };
          }
          if (patch.adaptationType && shot.sourceRanges.length === 0) return shot;
          return { ...shot, ...patch };
        }),
      })),
    })),
  };
}

export function bindShotSource(
  plan: AdaptationCandidate,
  shotKey: string,
  sourceRange: SourceRange,
): AdaptationCandidate {
  const location = findCandidateShot(plan, shotKey);
  if (!location) return plan;
  const next = cloneCandidate(plan);
  const beat = next.scenes[location.sceneIndex]?.beats[location.beatIndex];
  const shot = beat?.shots[location.shotIndex];
  if (!beat || !shot) return plan;
  beat.sourceRanges = mergeSourceRanges([...beat.sourceRanges, sourceRange]);
  shot.adaptationType = shot.adaptationType === "supplemental" ? "direct" : shot.adaptationType;
  shot.sourceRanges = [{ ...sourceRange }];
  return next;
}

export function addShotAfter(
  plan: AdaptationCandidate,
  afterShotKey: string,
  sourceRange: SourceRange | null,
  purpose: CandidateShot["narrativePurpose"],
): AdaptationCandidate | null {
  const location = findCandidateShot(plan, afterShotKey);
  if (!location) return null;
  const next = cloneCandidate(plan);
  const beat = next.scenes[location.sceneIndex]?.beats[location.beatIndex];
  if (!beat) return null;
  const shot: CandidateShot = {
    shotKey: "S999",
    title: purposeLabel(purpose),
    narrativePurpose: purpose,
    adaptationType: sourceRange ? "direct" : "supplemental",
    shotScale: purpose === "insert" ? "close" : purpose === "establishing" ? "long" : "medium_close",
    cameraAngle: "eye_level",
    cameraMovement: "locked",
    visualIntent: sourceRange
      ? "根据选中原文设计一个连续机位和一个主要可见动作。"
      : "补充当前戏剧节拍所需的建立、反应、插入或转场画面，不新增剧情结果。",
    audioMode: "ambient",
    audioIntent: "延续相邻镜头的环境声，不擅自新增对白。",
    cutReason: `人工新增${purposeLabel(purpose)}，用于完成当前戏剧节拍的画面关系`,
    timelineDurationMs: purpose === "reaction" || purpose === "insert" ? 1500 : 3000,
    sourceRanges: sourceRange ? [{ ...sourceRange }] : [],
  };
  if (sourceRange) beat.sourceRanges = mergeSourceRanges([...beat.sourceRanges, sourceRange]);
  beat.shots.splice(location.shotIndex + 1, 0, shot);
  return renumberCandidate(next);
}

export function mergeShotWithNext(
  plan: AdaptationCandidate,
  shotKey: string,
): AdaptationCandidate | null {
  const location = findCandidateShot(plan, shotKey);
  if (!location) return null;
  const currentBeat = plan.scenes[location.sceneIndex]?.beats[location.beatIndex];
  const current = currentBeat?.shots[location.shotIndex];
  const following = currentBeat?.shots[location.shotIndex + 1];
  if (!current || !following) return null;
  const ranges = uniqueRanges([...current.sourceRanges, ...following.sourceRanges]);
  if (ranges.length > 12 || current.timelineDurationMs + following.timelineDurationMs > 15_000) return null;
  const next = cloneCandidate(plan);
  const beat = next.scenes[location.sceneIndex]?.beats[location.beatIndex];
  if (!beat) return null;
  const merged: CandidateShot = {
    ...current,
    title: `${current.title} / ${following.title}`,
    adaptationType: ranges.length ? current.adaptationType === "supplemental" ? "direct" : current.adaptationType : "supplemental",
    sourceRanges: ranges,
    visualIntent: `${current.visualIntent}；随后${following.visualIntent}`,
    audioIntent: `${current.audioIntent}；随后${following.audioIntent}`,
    cutReason: current.cutReason,
    timelineDurationMs: current.timelineDurationMs + following.timelineDurationMs,
  };
  beat.shots.splice(location.shotIndex, 2, merged);
  return renumberCandidate(next);
}

export function mergeSceneWithNext(
  plan: AdaptationCandidate,
  sceneKey: string,
): AdaptationCandidate | null {
  const index = plan.scenes.findIndex((scene) => scene.sceneKey === sceneKey);
  const current = plan.scenes[index];
  const following = plan.scenes[index + 1];
  if (!current || !following) return null;
  const next = cloneCandidate(plan);
  next.scenes.splice(index, 2, {
    ...current,
    title: `${current.title} / ${following.title}`,
    locationLabel: joinDistinct(current.locationLabel, following.locationLabel),
    timeLabel: joinDistinct(current.timeLabel, following.timeLabel),
    objective: `${current.objective}；随后${following.objective}`,
    changeSummary: `${current.changeSummary}；随后${following.changeSummary}`,
    beats: [...current.beats, ...following.beats],
  });
  return renumberCandidate(next);
}

export function deleteCandidateShot(
  plan: AdaptationCandidate,
  shotKey: string,
): { plan: AdaptationCandidate; discarded: DiscardedShot } | null {
  if (flattenCandidateShots(plan).length <= 1) return null;
  const location = findCandidateShot(plan, shotKey);
  if (!location) return null;
  const next = cloneCandidate(plan);
  const beat = next.scenes[location.sceneIndex]?.beats[location.beatIndex];
  if (!beat || beat.shots.length <= 1) return null;
  const [shot] = beat.shots.splice(location.shotIndex, 1);
  return {
    plan: renumberCandidate(next),
    discarded: { shot, beatKey: beat.beatKey, ...location },
  };
}

export function restoreCandidateShot(
  plan: AdaptationCandidate,
  discarded: DiscardedShot,
): AdaptationCandidate | null {
  const next = cloneCandidate(plan);
  const beat = next.scenes
    .flatMap((scene) => scene.beats)
    .find((item) => item.beatKey === discarded.beatKey)
    ?? next.scenes[discarded.sceneIndex]?.beats[discarded.beatIndex];
  if (!beat) return null;
  beat.shots.splice(Math.min(discarded.shotIndex, beat.shots.length), 0, discarded.shot);
  return renumberCandidate(next);
}

export function candidateSourceCoverage(plan: AdaptationCandidate, sourceLength: number): number {
  if (!sourceLength) return 0;
  const ranges = uniqueRanges(flattenCandidateShots(plan).flatMap((shot) => shot.sourceRanges));
  const merged: Array<{ start: number; end: number }> = [];
  ranges.forEach((range) => {
    const previous = merged.at(-1);
    if (previous && range.start <= previous.end) previous.end = Math.max(previous.end, range.end);
    else merged.push({ start: range.start, end: range.end });
  });
  const covered = merged.reduce((total, range) => total + range.end - range.start, 0);
  return Math.round((covered / sourceLength) * 100);
}

export function buildSourceSegments(sourceText: string, plan: AdaptationCandidate): SourceSegment[] {
  return buildSourceSegmentsFromShots(sourceText, flattenCandidateShots(plan));
}

export function buildSourceSegmentsFromShots(
  sourceText: string,
  shots: Array<{ shotKey: string; sourceRanges: SourceRange[] }>,
): SourceSegment[] {
  const characters = Array.from(sourceText);
  const boundaries = new Set([0, characters.length]);
  shots.forEach((shot) => shot.sourceRanges.forEach((range) => {
    boundaries.add(range.start);
    boundaries.add(range.end);
  }));
  const ordered = [...boundaries].sort((left, right) => left - right);
  return ordered.slice(0, -1).map((start, index) => {
    const end = ordered[index + 1] ?? start;
    return {
      start,
      end,
      text: characters.slice(start, end).join(""),
      shotKeys: shots
        .filter((shot) => shot.sourceRanges.some((range) => range.start <= start && range.end >= end))
        .map((shot) => shot.shotKey),
    };
  });
}

export function durationMetrics(shots: Array<Pick<CandidateShot, "timelineDurationMs">>) {
  const totalMs = shots.reduce((total, shot) => total + shot.timelineDurationMs, 0);
  return {
    totalMs,
    averageMs: shots.length ? Math.round(totalMs / shots.length) : 0,
    fastCount: shots.filter((shot) => shot.timelineDurationMs <= 2000).length,
    standardCount: shots.filter((shot) => shot.timelineDurationMs > 2000 && shot.timelineDurationMs <= 4000).length,
    slowCount: shots.filter((shot) => shot.timelineDurationMs > 4000).length,
  };
}

export function groupFormalEpisodes(plan: FormalPlan, breakAfterShotIds: string[]): FormalShot[][] {
  const breaks = new Set(breakAfterShotIds);
  const groups: FormalShot[][] = [];
  let current: FormalShot[] = [];
  flattenFormalShots(plan).forEach((shot) => {
    current.push(shot);
    if (breaks.has(shot.id)) {
      groups.push(current);
      current = [];
    }
  });
  if (current.length) groups.push(current);
  return groups;
}

function findCandidateShot(plan: AdaptationCandidate, shotKey: string) {
  for (let sceneIndex = 0; sceneIndex < plan.scenes.length; sceneIndex += 1) {
    const scene = plan.scenes[sceneIndex];
    for (let beatIndex = 0; beatIndex < (scene?.beats.length ?? 0); beatIndex += 1) {
      const beat = scene?.beats[beatIndex];
      const shotIndex = beat?.shots.findIndex((shot) => shot.shotKey === shotKey) ?? -1;
      if (shotIndex >= 0) return { sceneIndex, beatIndex, shotIndex };
    }
  }
  return null;
}

function uniqueRanges(ranges: SourceRange[]): SourceRange[] {
  const values = new Map<string, SourceRange>();
  ranges.forEach((range) => values.set(`${range.start}:${range.end}:${range.sourceText}`, { ...range }));
  return [...values.values()].sort((left, right) => left.start - right.start);
}

function mergeSourceRanges(ranges: SourceRange[]): SourceRange[] {
  const ordered = uniqueRanges(ranges);
  const merged: SourceRange[] = [];
  ordered.forEach((range) => {
    const previous = merged.at(-1);
    if (!previous || range.start >= previous.end) {
      merged.push({ ...range });
      return;
    }
    if (range.end <= previous.end) return;
    const overlap = Math.max(0, previous.end - range.start);
    const suffix = Array.from(range.sourceText).slice(overlap).join("");
    previous.end = range.end;
    previous.sourceText += suffix;
  });
  return merged;
}

function joinDistinct(left: string, right: string): string {
  return left.trim() === right.trim() ? left : `${left} / ${right}`;
}

function key(prefix: string, number: number): string {
  return `${prefix}${String(number).padStart(2, "0")}`;
}

export function purposeLabel(purpose: CandidateShot["narrativePurpose"]): string {
  const labels: Record<CandidateShot["narrativePurpose"], string> = {
    establishing: "建立镜头",
    action: "动作镜头",
    dialogue: "对白镜头",
    reaction: "反应镜头",
    reveal: "揭示镜头",
    insert: "插入镜头",
    transition: "转场镜头",
    atmosphere: "氛围镜头",
  };
  return labels[purpose];
}
