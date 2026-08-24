import type { components } from "@inkforge/api-client";

import type { SelectionBridge } from "@/features/editor/selection-identity";

export type ChapterAdaptation = components["schemas"]["ChapterAdaptationResponse"];
export type AdaptationCandidate = components["schemas"]["ChapterAdaptationPlanCandidate"];
export type CandidateScene = components["schemas"]["CinematicSceneCandidate"];
export type CandidateBeat = components["schemas"]["DramaticBeatCandidate"];
export type CandidateShot = components["schemas"]["CinematicShotCandidate"];
export type CoverageGoal = components["schemas"]["BeatCoverageGoal"];
export type ReviewFinding = components["schemas"]["CinematicReviewFinding"];
export type SourceRange = components["schemas"]["ChapterAdaptationSourceRange"];
export type FormalPlan = components["schemas"]["FormalChapterAdaptationPlan"];
export type FormalScene = components["schemas"]["FormalCinematicScene"];
export type FormalBeat = components["schemas"]["FormalDramaticBeat"];
export type FormalShot = components["schemas"]["FormalCinematicShot"];
export type PromptCandidate = components["schemas"]["ShotPromptCandidateResponse"];
export type PromptVersion = components["schemas"]["ShotPromptVersionResponse"];
export type ShotVisualReference = components["schemas"]["ShotVisualReferenceSnapshot"];
export type ShotVisualReferenceSet = components["schemas"]["ShotVisualReferenceSetResponse"];
export type VisualCanon = components["schemas"]["VisualCanonResponse"];
export type VisualCanonVersion = components["schemas"]["VisualCanonVersionResponse"];
export type VideoAsset = components["schemas"]["VideoAssetResponse"];
export type CharacterSetting = components["schemas"]["CharacterResponse"];
export type LocationSetting = components["schemas"]["LocationResponse"];
export type ItemSetting = components["schemas"]["ItemResponse"];
export type VideoProject = components["schemas"]["VideoProjectResponse"];
export type RenderWorkspace = components["schemas"]["ChapterRenderWorkspaceResponse"];
export type RenderTask = components["schemas"]["ShotRenderTaskResponse"];
export type ShotTake = components["schemas"]["ShotTakeResponse"];
export type ShotTakeHead = components["schemas"]["ShotTakeHeadResponse"];
export type PostProductionWorkspace = components["schemas"]["ChapterPostProductionWorkspaceResponse"];
export type PostProductionEpisode = components["schemas"]["EpisodePostProductionResponse"];
export type KeyframeRole = components["schemas"]["SaveShotKeyframeVersionRequest"]["role"];
export type EpisodeEditClip = components["schemas"]["EpisodeEditClipInput"];
export type EpisodeEditVersion = components["schemas"]["EpisodeEditVersionResponse"];
export type EpisodeAudioClip = components["schemas"]["EpisodeAudioClipInput"];
export type EpisodeSubtitleCue = components["schemas"]["EpisodeSubtitleCueInput"];
export type EpisodeMixVersion = components["schemas"]["EpisodeMixVersionResponse"];
export type AudioTrackKind = components["schemas"]["EpisodeAudioClipInput"]["trackKind"];

export type ChapterAdaptationWorkspaceProps = {
  novelId: string;
  novelName: string;
  currentChapter?: {
    id: string;
    title: string;
    content: string;
    updatedAt: string;
  };
  selectionBridge?: SelectionBridge;
};

export type SourceSelection = SourceRange & {
  utf16Start: number;
  utf16End: number;
};
