import type { components } from "@inkforge/api-client";
import { expect, type APIResponse, type Page } from "@playwright/test";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export const E2E_PASSWORD = "e2e-pass-123";

type NovelIdentity = Pick<
  components["schemas"]["CreateNovelResponse"],
  "novelId" | "chapterId"
>;

export type ShortStoryOperation = "develop_short_outline" | "write_short_story";
export type ShortStoryOutlinePayload = components["schemas"]["ShortStoryOutlineDraft"];
export type ShortStoryDraftPayload = components["schemas"]["ShortStoryChapterDraft"];
export type ShortStoryArtifact = components["schemas"]["ShortStoryArtifactResponse"];
export type ShortStoryAggregate = components["schemas"]["ShortStoryArtifactsResponse"];
type ShortStoryDecision = components["schemas"]["ReviewArtifactDecisionRequest"]["decision"];
type ShortStoryRunAccepted = Pick<
  components["schemas"]["WritingRunResponse"],
  "id" | "commandId"
>;
type ShortStoryDecisionAccepted = Pick<
  components["schemas"]["ArtifactDecisionAcceptedResponse"],
  "taskId" | "commandId"
>;

type OutlineNodeIdentity = {
  id: string;
};

export function uniqueUsername(prefix: string): string {
  const suffix = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
  return `${prefix}${suffix}`.slice(0, 32);
}

export async function createNovelWithApi(
  page: Page,
  name = `端到端小说-${Date.now()}`,
): Promise<NovelIdentity> {
  const response = await page.request.post("/api/v1/novels", {
    data: {
      name,
      summary: "端到端测试项目",
      storyLengthProfile: "long_serial",
      targetTotalWordCount: 50_000,
      genre: "测试",
      protagonist: "测试主角",
      coreSellingPoint: "验证完整迁移链路",
      readerPromise: "所有关键流程可恢复",
      firstChapterGoal: "完成端到端验证",
    },
  });
  await expectApiOk(response, "创建测试小说");
  return (await response.json()) as NovelIdentity;
}

export async function createShortNovelWithApi(
  page: Page,
  targetTotalWordCount: number | null = null,
  name = `端到端中短篇-${Date.now()}`,
): Promise<NovelIdentity> {
  const response = await page.request.post("/api/v1/novels", {
    data: {
      storyLengthProfile: "short_medium",
      name,
      inspiration: "一个人收到来自未来自己的信，却发现寄信日期是自己的死期。",
      targetTotalWordCount,
    },
  });
  await expectApiOk(response, "创建中短篇测试小说");
  return (await response.json()) as NovelIdentity;
}

function uniqueClientRequestId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function countShortStoryTextLength(text: string): number {
  const ignored = /[\u0009-\u000d\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]/gu;
  return Array.from(text.replace(ignored, "")).length;
}

export async function createShortStorySessionWithApi(
  page: Page,
  identity: NovelIdentity,
): Promise<string> {
  const response = await page.request.post("/api/v1/writing/sessions", {
    data: {
      novelId: identity.novelId,
      chapterId: identity.chapterId,
      title: "中短篇端到端验收",
    },
  });
  await expectApiOk(response, "创建中短篇写作会话");
  return ((await response.json()) as components["schemas"]["WritingSessionResponse"]).id;
}

export async function startShortStoryOperationWithApi(
  page: Page,
  identity: NovelIdentity,
  writingSessionId: string,
  operation: ShortStoryOperation,
  targetWordCount: number | null,
  userMessage: string,
): Promise<ShortStoryRunAccepted> {
  const response = await page.request.post("/api/v1/writing/runs", {
    data: {
      clientRequestId: uniqueClientRequestId(operation),
      novelId: identity.novelId,
      chapterId: identity.chapterId,
      writingSessionId,
      workflowKind: "short_medium",
      operation,
      targetWordCount,
      userMessage,
    },
  });
  await expectApiOk(response, `启动中短篇操作 ${operation}`);
  return (await response.json()) as ShortStoryRunAccepted;
}

export async function decideShortStoryArtifactWithApi(
  page: Page,
  artifact: Pick<ShortStoryArtifact, "id" | "revision">,
  decision: ShortStoryDecision,
  userMessage?: string,
): Promise<ShortStoryDecisionAccepted> {
  const response = await page.request.post(
    `/api/v1/review-artifacts/${artifact.id}/decision`,
    {
      data: {
        clientRequestId: uniqueClientRequestId(`short-${decision}`),
        decision,
        expectedRevision: artifact.revision,
        ...(userMessage ? { userMessage } : {}),
      },
    },
  );
  await expectApiOk(response, `提交中短篇草案决定 ${decision}`);
  return (await response.json()) as ShortStoryDecisionAccepted;
}

export async function readShortStoryAggregate(
  page: Page,
  novelId: string,
): Promise<ShortStoryAggregate> {
  const response = await page.request.get(
    `/api/v1/novels/${novelId}/short-story/artifacts`,
  );
  await expectApiOk(response, "读取中短篇聚合状态");
  return (await response.json()) as ShortStoryAggregate;
}

export async function waitForShortStoryAggregate(
  page: Page,
  novelId: string,
  predicate: (aggregate: ShortStoryAggregate) => boolean,
  description: string,
  timeout = 90_000,
): Promise<ShortStoryAggregate> {
  let latest: ShortStoryAggregate | null = null;
  await expect.poll(
    async () => {
      latest = await readShortStoryAggregate(page, novelId);
      return predicate(latest);
    },
    { timeout, message: description },
  ).toBe(true);
  if (!latest) throw new Error(`${description}失败：没有取得中短篇聚合状态`);
  return latest;
}

export async function readWorkspace(
  page: Page,
  novelId: string,
): Promise<Record<string, unknown>> {
  const response = await page.request.get(`/api/v1/novels/${novelId}/workspace`);
  await expectApiOk(response, "读取工作区");
  return (await response.json()) as Record<string, unknown>;
}

export async function readChapterWithApi(
  page: Page,
  chapterId: string,
): Promise<components["schemas"]["WorkspaceChapter"]> {
  const response = await page.request.get(`/api/v1/chapters/${chapterId}`);
  await expectApiOk(response, "读取正文 Chapter");
  return (await response.json()) as components["schemas"]["WorkspaceChapter"];
}

export async function prepareWritingOutlineWithApi(
  page: Page,
  identity: NovelIdentity,
): Promise<void> {
  const createNode = async (data: Record<string, unknown>): Promise<OutlineNodeIdentity> => {
    const response = await page.request.post(
      `/api/v1/novels/${identity.novelId}/outline-nodes`,
      { data },
    );
    await expectApiOk(response, "创建结构化大纲节点");
    return (await response.json()) as OutlineNodeIdentity;
  };

  const stage = await createNode({
    title: "端到端阶段",
    kind: "stage",
    status: "planned",
    order: 1,
    chapterStartOrder: 1,
    chapterEndOrder: 1,
  });
  const plotUnit = await createNode({
    title: "端到端情节单元",
    kind: "plot_unit",
    status: "planned",
    order: 1,
    parentId: stage.id,
    chapterStartOrder: 1,
    chapterEndOrder: 1,
  });
  await createNode({
    title: "端到端章节组",
    kind: "chapter_group",
    status: "planned",
    order: 1,
    parentId: plotUnit.id,
    linkedChapterId: identity.chapterId,
    chapterStartOrder: 1,
    chapterEndOrder: 1,
  });
}

export async function expectApiOk(
  response: APIResponse,
  action: string,
): Promise<void> {
  if (!response.ok()) {
    throw new Error(`${action}失败：${response.status()} ${await response.text()}`);
  }
}

export async function openWorkspace(page: Page, identity: NovelIdentity): Promise<void> {
  await page.goto(`/workspace/${identity.novelId}?chapterId=${identity.chapterId}`);
  await expect(page.getByRole("button", { name: "AI 创作", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(
    page.getByPlaceholder("描述要完成的创作任务，系统会自动分配合适的 Agent"),
  ).toBeVisible();
}

export async function seedInvalidQualityCheck(checkId: string): Promise<void> {
  if (!process.env.DATABASE_URL) process.loadEnvFile(".env.local");
  await execFileAsync(
    "uv",
    ["run", "python", "tests/e2e/seed_invalid_quality_check.py", checkId],
    { cwd: process.cwd(), env: process.env },
  );
}

export async function openReadingWorkspace(
  page: Page,
  identity: NovelIdentity,
): Promise<void> {
  await page.goto(
    `/workspace/${identity.novelId}?chapterId=${identity.chapterId}&view=reading`,
  );
  await expect(page.getByRole("button", { name: "阅读与小修", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByRole("button", { name: "进入小修", exact: true })).toBeVisible();
  await expect(page.getByPlaceholder("正文内容")).toHaveCount(0);
}

export async function enterMinorEdit(page: Page): Promise<void> {
  await page.getByRole("button", { name: "进入小修", exact: true }).click();
  await expect(page.getByPlaceholder("章节标题")).toBeVisible();
  await expect(page.getByPlaceholder("正文内容")).toBeEditable();
}
