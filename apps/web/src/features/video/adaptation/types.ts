import type { components } from "@inkforge/api-client";

import type { SelectionBridge } from "@/features/editor/selection-identity";

export type ChapterAdaptation = components["schemas"]["ChapterAdaptationResponse"];
export type AdaptationCandidate = components["schemas"]["ChapterAdaptationPlanCandidate"];
export type CandidateScene = components["schemas"]["CinematicSceneCandidate"];
export type CandidateBeat = components["schemas"]["DramaticBeatCandidate"];
export type CandidateShot = components["schemas"]["CinematicShotCandidate"];
export type SourceRange = components["schemas"]["ChapterAdaptationSourceRange"];
export type FormalPlan = components["schemas"]["FormalChapterAdaptationPlan"];
export type FormalScene = components["schemas"]["FormalCinematicScene"];
export type FormalBeat = components["schemas"]["FormalDramaticBeat"];
export type FormalShot = components["schemas"]["FormalCinematicShot"];
export type PromptCandidate = components["schemas"]["ShotPromptCandidateResponse"];
export type PromptVersion = components["schemas"]["ShotPromptVersionResponse"];
export type VideoProject = components["schemas"]["VideoProjectResponse"];

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
