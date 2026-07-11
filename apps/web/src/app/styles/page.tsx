import Link from "next/link";
import { redirect } from "next/navigation";

import { StyleLibraryPanel } from "@/features/styles/style-library-panel";
import { createServerApiClient } from "@/lib/api/server";
import { CoreApiPageError, requireApiData } from "@/lib/api/response";

export default async function StylesPage() {
  let styles;
  try {
    const client = await createServerApiClient();
    styles = requireApiData(await client.GET("/api/v1/styles"));
  } catch (error) {
    if (error instanceof CoreApiPageError && error.status === 401) redirect("/login");
    const message = error instanceof Error ? error.message : "加载文风库失败";
    return <main className="page"><div className="empty">{message}</div></main>;
  }

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
            <Link href="/dashboard" className="muted">
              ← 返回工作台
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
