/**
 * 当前写作任务待用户审核草案查询 API。
 *
 * 用于兜底恢复前端审核入口：即使 SSE 审核事件丢失，前端也能按 taskId 查询
 * 最新 awaiting_user ReviewArtifact。
 */

import { NextRequest } from "next/server";

import { toReviewArtifactDtoWithFreshDiff } from "@/agents/artifacts/artifact-service";
import { authorizeWritingTask, authErrorResponse } from "@/agents/lib/task-auth";
import { prisma } from "@/shared/db/prisma";
import { getSession } from "@/shared/lib/auth";
import { logger } from "@/shared/lib/logger";
import { deserializeGraphStateSnapshot } from "@/agents/graph/graph-state-snapshot";

export const dynamic = "force-dynamic";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ taskId: string }> }
) {
  const { taskId } = await params;

  try {
    const currentSession = await getSession();
    if (!currentSession) return authErrorResponse("未登录", 401);

    const auth = await authorizeWritingTask(taskId, currentSession.userId);
    if (!auth.authorized) return authErrorResponse(auth.reason ?? "无权访问该任务", 403);

    const task = await prisma.writingTask.findUnique({
      where: { id: taskId },
      select: {
        phase: true,
        generatedContent: true,
        graphStateJson: true,
      },
    });

    const snapshot = deserializeGraphStateSnapshot(task?.graphStateJson);
    const artifactId = snapshot?.artifactReview.activeArtifactId ?? snapshot?.activeArtifactId ?? task?.generatedContent ?? null;

    if (task?.phase !== "awaiting_user_review" || !artifactId) {
      return Response.json({ artifact: null });
    }

    const artifact = await prisma.reviewArtifact.findFirst({
      where: {
        id: artifactId,
        taskId,
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
    logger.error("API", "查询待用户审核草案失败", { taskId, error });
    return new Response(JSON.stringify({ error: "查询待用户审核草案失败" }), { status: 500 });
  }
}
