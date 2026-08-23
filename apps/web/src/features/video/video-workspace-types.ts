import type { SelectionBridge } from "@/features/editor/selection-identity";

export type VideoWorkspaceProps = {
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
