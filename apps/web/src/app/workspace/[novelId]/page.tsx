import type { components } from "@inkforge/api-client";
import { notFound, redirect } from "next/navigation";

import { WorkspaceShell } from "@/features/workspace/workspace-shell";
import { parseWorkspaceView } from "@/features/workspace/workspace-view";
import { createServerApiClient } from "@/lib/api/server";
import { CoreApiPageError, requireApiData } from "@/lib/api/response";

type WorkspacePageProps = {
  params: Promise<{ novelId: string }>;
  searchParams: Promise<{ chapterId?: string; view?: string | string[] }>;
};

export default async function WorkspacePage({
  params,
  searchParams,
}: WorkspacePageProps) {
  const { novelId } = await params;
  const { chapterId, view } = await searchParams;
  const workspaceView = parseWorkspaceView(view);
  let workspace: components["schemas"]["WorkspaceBootstrapResponse"];
  let currentUser: components["schemas"]["UserResponse"];
  try {
    const client = await createServerApiClient();
    const [workspaceResult, currentUserResult] = await Promise.all([
      client.GET(
        "/api/v1/novels/{novel_id}/workspace/bootstrap",
        {
          params: {
            path: { novel_id: novelId },
            query: { chapterId },
          },
        },
      ),
      client.GET("/api/v1/auth/me"),
    ]);
    workspace = requireApiData(workspaceResult);
    currentUser = requireApiData(currentUserResult);
  } catch (error) {
    if (error instanceof CoreApiPageError && error.status === 401) redirect("/login");
    if (error instanceof CoreApiPageError && error.status === 404) notFound();
    const message = error instanceof Error ? error.message : "加载作品工作区失败";
    return <main className="page"><div className="empty">{message}</div></main>;
  }

  return (
    <WorkspaceShell
      bootstrap={workspace}
      currentUser={currentUser}
      initialView={workspaceView}
    />
  );
}
