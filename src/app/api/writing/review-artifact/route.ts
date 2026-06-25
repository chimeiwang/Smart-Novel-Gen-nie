/**
 * 当前小说/章节待审核草案查询 API。
 *
 * 用于页面刷新、热更新或 SSE 事件丢失后的持久状态恢复。
 */

import { NextRequest } from "next/server";

import {
  toReviewArtifactDtosWithFreshDiff,
  toReviewArtifactDtoWithFreshDiff,
} from "@/agents/artifacts/artifact-service";
import { authorizeNovel, authErrorResponse } from "@/agents/lib/task-auth";
import { prisma } from "@/shared/db/prisma";
import { getSession } from "@/shared/lib/auth";
import { logger } from "@/shared/lib/logger";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const novelId = searchParams.get("novelId");
  const chapterId = searchParams.get("chapterId");

  try {
    const currentSession = await getSession();
    if (!currentSession) return authErrorResponse("未登录", 401);

    if (!novelId) {
      return new Response(JSON.stringify({ error: "缺少 novelId" }), { status: 400 });
    }

    const auth = await authorizeNovel(novelId, currentSession.userId);
    if (!auth.authorized) return authErrorResponse(auth.reason ?? "无权访问该小说", 403);

    if (!chapterId) {
      const artifacts = await prisma.reviewArtifact.findMany({
        where: {
          novelId,
          status: "awaiting_user",
        },
        include: {
          evaluations: {
            orderBy: { createdAt: "asc" },
          },
        },
        orderBy: [
          { updatedAt: "desc" },
          { createdAt: "desc" },
        ],
        take: 20,
      });

      return Response.json({
        artifacts: await toReviewArtifactDtosWithFreshDiff(artifacts),
      });
    }

    const artifact = await prisma.reviewArtifact.findFirst({
      where: {
        novelId,
        chapterId,
        status: "awaiting_user",
      },
      include: {
        evaluations: {
          orderBy: { createdAt: "asc" },
        },
      },
      orderBy: [
        { updatedAt: "desc" },
        { createdAt: "desc" },
      ],
    });

    return Response.json({
      artifact: artifact ? await toReviewArtifactDtoWithFreshDiff(artifact) : null,
    });
  } catch (error) {
    logger.error("API", "查询待审核草案失败", { novelId, chapterId, error });
    return new Response(JSON.stringify({ error: "查询待审核草案失败" }), { status: 500 });
  }
}
