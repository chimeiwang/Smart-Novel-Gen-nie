import type { Metadata } from "next";

import { getSession } from "@/shared/lib/auth";
import { prisma } from "@/shared/db/prisma";
import { UserMenu } from "@/features/auth/user-menu";
import { logger } from "@/shared/lib/logger";
import { normalizeTokenUsageBreakdown, type TokenUsageBreakdown } from "@/shared/lib/token-cost";

import "./globals.css";

export const metadata: Metadata = {
  title: "智能小说创作工具",
  description: "本地优先的智能小说创作工作台",
};

async function getUserMenuData(session: { userId: string } | null): Promise<{
  username: string | null;
  monthlyUsage: TokenUsageBreakdown;
}> {
  if (!session) return { username: null, monthlyUsage: normalizeTokenUsageBreakdown() };

  try {
    const user = await prisma.user.findUnique({
      where: { id: session.userId },
      select: { username: true },
    });

    if (!user) return { username: null, monthlyUsage: normalizeTokenUsageBreakdown() };

    const monthStart = new Date();
    monthStart.setDate(1);
    monthStart.setHours(0, 0, 0, 0);

    const monthlyResult = await prisma.tokenUsage.aggregate({
      where: {
        userId: session.userId,
        createdAt: { gte: monthStart },
      },
      _sum: {
        promptTokens: true,
        cachedTokens: true,
        completionTokens: true,
        totalTokens: true,
      },
    });

    return {
      username: user.username,
      monthlyUsage: normalizeTokenUsageBreakdown({
        promptTokens: monthlyResult._sum.promptTokens ?? 0,
        cachedTokens: monthlyResult._sum.cachedTokens ?? 0,
        completionTokens: monthlyResult._sum.completionTokens ?? 0,
        totalTokens: monthlyResult._sum.totalTokens ?? 0,
      }),
    };
  } catch (error) {
    logger.warn("AUTH", "加载用户菜单数据失败", {
      userId: session.userId,
      error: error instanceof Error ? error.message : String(error),
    });
    return { username: null, monthlyUsage: normalizeTokenUsageBreakdown() };
  }
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const session = await getSession();
  const { username, monthlyUsage } = await getUserMenuData(session);

  return (
    <html lang="zh-CN">
      <body>
        {session && username && (
          <UserMenu username={username} monthlyUsage={monthlyUsage} />
        )}
        {children}
      </body>
    </html>
  );
}
