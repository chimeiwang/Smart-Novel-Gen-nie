import { expect, type APIResponse, type Page } from "@playwright/test";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export const E2E_PASSWORD = "e2e-pass-123";

type NovelIdentity = {
  novelId: string;
  chapterId: string;
};

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
      storyLengthProfile: "short_medium",
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

export async function readWorkspace(page: Page, novelId: string): Promise<Record<string, unknown>> {
  const response = await page.request.get(`/api/v1/novels/${novelId}/workspace`);
  await expectApiOk(response, "读取工作区");
  return (await response.json()) as Record<string, unknown>;
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
