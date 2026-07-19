type ShortStoryContentProps = {
  content: string;
  emptyLabel?: string;
};

export function ShortStoryContent({
  content,
  emptyLabel = "正文生成后会完整显示在这里。",
}: ShortStoryContentProps) {
  if (!content) return <p className="empty">{emptyLabel}</p>;

  return <article className="short-story-content">{content}</article>;
}

