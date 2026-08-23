import type {
  AdaptationCandidate,
  CandidateBeat,
  CandidateShot,
  FormalPlan,
  FormalShot,
  ReviewFinding,
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
        coverageGoals: beat.coverageGoals.map((goal) => ({ ...goal })),
        sourceRanges: beat.sourceRanges.map((range) => ({ ...range })),
        shots: beat.shots.map((shot) => ({
          ...shot,
          coveredGoalKeys: [...(shot.coveredGoalKeys ?? [])],
          sourceRanges: shot.sourceRanges.map((range) => ({ ...range })),
        })),
      })),
    })),
    reviewFindings: (plan.reviewFindings ?? []).map((finding) => ({ ...finding })),
  };
}

export function flattenCandidateShots(plan: AdaptationCandidate): CandidateShot[] {
  return plan.scenes.flatMap((scene) => scene.beats.flatMap((beat) => beat.shots));
}

export function flattenFormalShots(plan: FormalPlan): FormalShot[] {
  return plan.scenes.flatMap((scene) => scene.beats.flatMap((beat) => beat.shots));
}

export function renumberCandidate(plan: AdaptationCandidate): AdaptationCandidate {
  const sceneKeyMap = new Map<string, string>();
  const beatKeyMap = new Map<string, string>();
  const shotKeyMap = new Map<string, string>();
  let beatNumber = 0;
  let shotNumber = 0;
  const scenes = plan.scenes.map((scene, sceneIndex) => {
    const sceneKey = key("SC", sceneIndex + 1);
    sceneKeyMap.set(scene.sceneKey, sceneKey);
    return {
      ...scene,
      sceneKey,
      beats: scene.beats.map((beat) => {
      beatNumber += 1;
      const beatKey = key("B", beatNumber);
      beatKeyMap.set(beat.beatKey, beatKey);
      return {
        ...beat,
        beatKey,
        shots: beat.shots.map((shot) => {
          shotNumber += 1;
          const shotKey = key("S", shotNumber);
          shotKeyMap.set(shot.shotKey, shotKey);
          return { ...shot, shotKey };
        }),
      };
      }),
    };
  });
  const lastShotKey = key("S", shotNumber);
  return {
    ...plan,
    scenes,
    suggestedEpisodeBreakAfterShotKeys: (plan.suggestedEpisodeBreakAfterShotKeys ?? [])
      .map((shotKey) => shotKeyMap.get(shotKey))
      .filter((shotKey): shotKey is string => Boolean(shotKey) && shotKey !== lastShotKey),
    reviewFindings: (plan.reviewFindings ?? []).flatMap((finding) => {
      if (finding.scope === "plan") return [finding];
      const mapped = finding.scope === "scene"
        ? sceneKeyMap.get(finding.scopeKey ?? "")
        : finding.scope === "beat"
          ? beatKeyMap.get(finding.scopeKey ?? "")
          : shotKeyMap.get(finding.scopeKey ?? "");
      return mapped ? [{ ...finding, scopeKey: mapped }] : [];
    }),
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
          if (patch.sourceRelation && patch.sourceRelation !== "supplemental" && shot.sourceRanges.length === 0) return shot;
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
    storyFunction: `补足当前节拍中的${purposeLabel(purpose)}职责`,
    audienceGain: "请说明这个镜头结束后观众新增的信息、情绪或空间认知。",
    coveredGoalKeys: [],
    sourceRelation: sourceRange ? "direct" : "supplemental",
    shotScale: purpose === "insert" ? "close" : purpose === "establishing" ? "long" : "medium_close",
    cameraAngle: "eye_level",
    cameraMovement: "locked",
    visualIntent: sourceRange
      ? "根据选中原文设计一个连续机位和一个主要可见动作。"
      : "补充当前戏剧节拍所需的建立、反应、插入或转场画面，不新增剧情结果。",
    speechMode: "none",
    spokenText: null,
    soundDesign: "延续相邻镜头的环境声，不擅自新增对白。",
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
  if (current.speechMode !== "none" && following.speechMode !== "none" && current.speechMode !== following.speechMode) return null;
  const ranges = uniqueRanges([...current.sourceRanges, ...following.sourceRanges]);
  if (ranges.length > 12 || current.timelineDurationMs + following.timelineDurationMs > 15_000) return null;
  const next = cloneCandidate(plan);
  const beat = next.scenes[location.sceneIndex]?.beats[location.beatIndex];
  if (!beat) return null;
  const merged: CandidateShot = {
    ...current,
    title: `${current.title} / ${following.title}`,
    storyFunction: `${current.storyFunction}；随后${following.storyFunction}`,
    audienceGain: `${current.audienceGain}；随后${following.audienceGain}`,
    coveredGoalKeys: [...new Set([
      ...(current.coveredGoalKeys ?? []),
      ...(following.coveredGoalKeys ?? []),
    ])],
    sourceRelation: mergedSourceRelation(current, following, ranges.length > 0),
    sourceRanges: ranges,
    visualIntent: `${current.visualIntent}；随后${following.visualIntent}`,
    speechMode: current.speechMode === "none" ? following.speechMode : current.speechMode,
    spokenText: [current.spokenText, following.spokenText].filter(Boolean).join("；") || null,
    soundDesign: `${current.soundDesign}；随后${following.soundDesign}`,
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

export function beatCoverageStatus(beat: Pick<CandidateBeat, "coverageGoals" | "shots">) {
  return beat.coverageGoals.map((goal) => ({
    ...goal,
    coveredBy: beat.shots
      .filter((shot) => (shot.coveredGoalKeys ?? []).includes(goal.goalKey))
      .map((shot) => shot.shotKey),
  }));
}

export function localCoverageFindings(plan: AdaptationCandidate): ReviewFinding[] {
  return plan.scenes.flatMap((scene) => scene.beats.flatMap((beat) => {
    const findings: ReviewFinding[] = beatCoverageStatus(beat)
      .filter((goal) => goal.coveredBy.length === 0)
      .map((goal) => ({
        severity: goal.priority === "essential" ? "warning" : "notice",
        scope: "beat",
        scopeKey: beat.beatKey,
        message: goal.priority === "essential" ? "必要叙事目标尚未覆盖" : "辅助叙事目标尚未覆盖",
        evidence: `${goal.goalKey} ${goal.description}`,
        suggestion: "让现有镜头承担该目标，或按作者判断调整目标，而不是机械新增镜头。",
      }));
    beat.shots.filter((shot) => (shot.coveredGoalKeys ?? []).length === 0).forEach((shot) => findings.push({
      severity: "notice",
      scope: "shot",
      scopeKey: shot.shotKey,
      message: "镜头尚未关联叙事目标",
      evidence: shot.storyFunction,
      suggestion: "确认它是否带来独立信息、情绪或空间认知；否则考虑合并或删除。",
    }));
    return findings;
  }));
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

function mergedSourceRelation(
  current: CandidateShot,
  following: CandidateShot,
  hasSource: boolean,
): CandidateShot["sourceRelation"] {
  if (!hasSource) return "supplemental";
  if (current.sourceRelation === following.sourceRelation) return current.sourceRelation;
  if (current.sourceRelation === "derived" || following.sourceRelation === "derived") return "derived";
  return "derived";
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
