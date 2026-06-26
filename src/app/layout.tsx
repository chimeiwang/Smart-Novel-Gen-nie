import type { Metadata } from "next";

import { getSession } from "@/shared/lib/auth";
import { prisma } from "@/shared/db/prisma";
import { UserMenu } from "@/features/auth/user-menu";
import { logger } from "@/shared/lib/logger";
import { formatCreditMicros } from "@/shared/lib/billing";

import "./globals.css";

export const metadata: Metadata = {
  title: "墨铸 InkForge",
  description: "面向中文小说作者的本地优先智能创作工作台",
};

async function getUserMenuData(session: { userId: string } | null): Promise<{
  username: string | null;
  creditBalance: string;
}> {
  if (!session) return { username: null, creditBalance: "0" };

  try {
    const user = await prisma.user.findUnique({
      where: { id: session.userId },
      select: { username: true, creditBalanceMicros: true },
    });

    if (!user) return { username: null, creditBalance: "0" };

    return {
      username: user.username,
      creditBalance: formatCreditMicros(user.creditBalanceMicros),
    };
  } catch (error) {
    logger.warn("AUTH", "加载用户菜单数据失败", {
      userId: session.userId,
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
  const session = await getSession();
  const { username, creditBalance } = await getUserMenuData(session);

  return (
    <html lang="zh-CN">
      <body>
        {session && username && (
          <UserMenu username={username} creditBalance={creditBalance} />
        )}
        {children}
      </body>
    </html>
  );
}
