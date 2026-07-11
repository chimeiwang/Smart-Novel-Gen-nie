import { redirect } from "next/navigation";

import { NovelListClient } from "@/features/projects/novel-list-client";
import { createServerApiClient } from "@/lib/api/server";
import { CoreApiPageError, requireApiData } from "@/lib/api/response";

export default async function DashboardPage() {
  try {
    const client = await createServerApiClient();
    const dashboard = requireApiData(await client.GET("/api/v1/dashboard"));
    return <NovelListClient novels={dashboard.novels} />;
  } catch (error) {
    if (error instanceof CoreApiPageError && error.status === 401) redirect("/login");
    const message = error instanceof Error ? error.message : "加载作品列表失败";
    return <main className="page"><div className="empty">{message}</div></main>;
  }
}
