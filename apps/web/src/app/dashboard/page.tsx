import type { components } from "@inkforge/api-client";
import { redirect } from "next/navigation";

import { NovelListClient } from "@/features/projects/novel-list-client";
import { createServerApiClient } from "@/lib/api/server";
import { CoreApiPageError, requireApiData } from "@/lib/api/response";

export default async function DashboardPage() {
  let dashboard: components["schemas"]["DashboardResponse"] | null = null;
  let loadError: string | null = null;
  try {
    const client = await createServerApiClient();
    dashboard = requireApiData(await client.GET("/api/v1/dashboard"));
  } catch (error) {
    if (error instanceof CoreApiPageError && error.status === 401) redirect("/login");
    loadError = error instanceof Error ? error.message : "加载作品列表失败";
  }
  if (loadError || !dashboard) {
    return <main className="page"><div className="empty">{loadError}</div></main>;
  }
  return <NovelListClient novels={dashboard.novels} />;
}
