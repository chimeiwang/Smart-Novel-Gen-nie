import type { WorkspaceView } from "@/features/workspace/workspace-view";

type ChapterEditorPresentationInput = {
  view: WorkspaceView;
  chapterStatus: string;
  minorEditing: boolean;
};

type ChapterEditorPresentation = {
  showEditableFields: boolean;
  showReadingContent: boolean;
  showEnterMinorEdit: boolean;
  readOnlyReason: string | null;
};

export function getChapterEditorPresentation({
  view,
  chapterStatus,
  minorEditing,
}: ChapterEditorPresentationInput): ChapterEditorPresentation {
  const isReading = view === "reading";
  const isDrafting = chapterStatus === "drafting";
  const showEditableFields = !isReading || (isDrafting && minorEditing);

  let readOnlyReason: string | null = null;
  if (chapterStatus === "review") {
    readOnlyReason = "章节正在审核中，请先退回草稿后再编辑。";
  } else if (chapterStatus === "completed") {
    readOnlyReason = "章节已完成，请先点击重新编辑后再修改。";
  }

  return {
    showEditableFields,
    showReadingContent: isReading && !showEditableFields,
    showEnterMinorEdit: isReading && isDrafting && !minorEditing,
    readOnlyReason,
  };
}
