import type { Metadata } from "next";

import { UserMenu } from "@/features/auth/user-menu";
import { createServerApiClient } from "@/lib/api/server";

import "./globals.css";

export const metadata: Metadata = {
  title: "墨铸 InkForge",
  description: "面向中文小说作者的本地优先智能创作工作台",
};

export const dynamic = "force-dynamic";

async function getUserMenuData(): Promise<{
  username: string | null;
  creditBalance: string;
}> {
  try {
    const client = await createServerApiClient();
    const { data, response } = await client.GET("/api/v1/billing/summary");
    if (response.status === 401 || !data) return { username: null, creditBalance: "0" };
    return {
      username: data.username,
      creditBalance: data.balanceCredits,
    };
  } catch (error) {
    console.warn("加载用户菜单数据失败", {
      error: error instanceof Error ? error.message : String(error),
    });
    return { username: null, creditBalance: "0" };
  }
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const { username, creditBalance } = await getUserMenuData();

  return (
    <html lang="zh-CN">
      <body>
        {username && (
          <UserMenu username={username} creditBalance={creditBalance} />
        )}
        {children}
      </body>
    </html>
  );
}
