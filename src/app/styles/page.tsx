import Link from "next/link";

import { StyleLibraryPanel } from "@/features/styles/style-library-panel";
import { prisma } from "@/shared/db/prisma";

export default async function StylesPage() {
  const styles = await prisma.writingStyle.findMany({
    orderBy: {
      updatedAt: "desc",
    },
    include: {
      references: {
        orderBy: {
          createdAt: "desc",
        },
      },
      tasks: {
        orderBy: {
          createdAt: "desc",
        },
        take: 1,
      },
    },
  });

  const styleList = styles.map((style) => ({
    id: style.id,
    name: style.name,
    sourceType: style.sourceType,
    creativeMethodology: style.creativeMethodology,
    uniqueMarkers: style.uniqueMarkers,
    generationStyle: style.generationStyle,
    expressionFeatures: style.expressionFeatures,
    styleTraits: style.styleTraits,
    portraitMarkdown: style.portraitMarkdown,
    originalCharCount: style.originalCharCount,
    usedCharCount: style.usedCharCount,
    truncated: style.truncated,
    errorMessage: style.errorMessage,
    references: style.references.map((ref) => ({
      id: ref.id,
      filename: ref.filename,
      charCount: ref.charCount,
      status: ref.status,
    })),
    latestTask: style.tasks[0]
      ? {
          id: style.tasks[0].id,
          status: style.tasks[0].status,
        }
      : null,
  }));

  return (
    <main className="page stack">
      <div className="panel">
        <div className="panel-header">
          <div className="stack">
            <Link href="/" className="muted">
              ← 返回首页
            </Link>
            <h1 className="title-lg">文风库</h1>
            <p className="muted">
              上传 txt 参考资料文件，自动提取五维度文风画像。小说工作台中只负责选择与应用。
            </p>
          </div>
        </div>
      </div>

      <StyleLibraryPanel styles={styleList} />
    </main>
  );
}