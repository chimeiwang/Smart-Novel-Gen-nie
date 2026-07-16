import { expect, test } from "@playwright/test";

import {
  createNovelWithApi,
  enterMinorEdit,
  expectApiOk,
  openReadingWorkspace,
  readWorkspace,
} from "./helpers";

test.use({ viewport: { width: 1440, height: 900 } });

test("新建小说默认进入创作工作室，阅读模式显式进入小修后自动保存", async ({ page }) => {
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "新建小说", exact: true }).click();

  const novelName = `浏览器创建-${Date.now()}`;
  await page.getByLabel("小说名称").fill(novelName);
  await page.getByRole("button", { name: /中短篇/ }).click();
  await page.getByLabel("作品简介").fill("浏览器端到端创建流程");
  await page.locator("form").getByRole("button", { name: "新建小说", exact: true }).click();
  await expect(page).toHaveURL(/\/workspace\/[^?]+/);
  await expect(page.getByRole("button", { name: "AI 创作", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByPlaceholder("章节标题")).not.toBeVisible();

  await page.getByRole("button", { name: "阅读与小修", exact: true }).click();
  await expect(page).toHaveURL(/view=reading/);
  await expect(page.getByRole("button", { name: "进入小修", exact: true })).toBeVisible();
  await expect(page.getByPlaceholder("正文内容")).toHaveCount(0);
  await enterMinorEdit(page);

  await page.getByPlaceholder("章节标题").fill("端到端第一章");
  await page.getByPlaceholder("正文内容").fill("这是通过浏览器输入并自动保存的完整章节正文。");
  await expect(page.getByText("已保存", { exact: true })).toBeVisible({ timeout: 20_000 });

  const novelId = new URL(page.url()).pathname.split("/").pop();
  expect(novelId).toBeTruthy();
  const workspace = await readWorkspace(page, novelId!);
  const chapters = workspace.chapters as Array<{ title: string; content: string }>;
  expect(chapters[0]).toMatchObject({
    title: "端到端第一章",
    content: "这是通过浏览器输入并自动保存的完整章节正文。",
  });
});

test("小修中快速输入后切换章节会先保存最新正文", async ({ page }) => {
  const identity = await createNovelWithApi(page);
  const createResponse = await page.request.post(
    `/api/v1/novels/${identity.novelId}/chapters`,
    { data: {} },
  );
  await expectApiOk(createResponse, "创建第二章");
  const secondChapter = (await createResponse.json()) as {
    chapter: { id: string; title: string };
  };
  await openReadingWorkspace(page, identity);
  await enterMinorEdit(page);

  await page.getByPlaceholder("章节标题").fill("切章前标题");
  await page.getByPlaceholder("正文内容").fill("切章前必须保存的最新正文");
  await page
    .locator("a.chapter-link")
    .filter({ hasText: secondChapter.chapter.title })
    .click();

  await expect(page).toHaveURL(
    new RegExp(`chapterId=${secondChapter.chapter.id}`),
  );
  const workspace = await readWorkspace(page, identity.novelId);
  const chapters = workspace.chapters as Array<{
    id: string;
    title: string;
    content: string;
  }>;
  expect(chapters.find((chapter) => chapter.id === identity.chapterId)).toMatchObject({
    title: "切章前标题",
    content: "切章前必须保存的最新正文",
  });
});

test("小修中切换到创作工作室会先保存最新正文", async ({ page }) => {
  const identity = await createNovelWithApi(page);
  await openReadingWorkspace(page, identity);
  await enterMinorEdit(page);

  await page.getByPlaceholder("章节标题").fill("切模式前标题");
  await page.getByPlaceholder("正文内容").fill("切模式前必须保存的最新正文");
  await page.getByRole("button", { name: "AI 创作", exact: true }).click();

  await expect(page).toHaveURL(/view=studio/);
  await expect(page.getByRole("button", { name: "AI 创作", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect.poll(async () => {
    const workspace = await readWorkspace(page, identity.novelId);
    const chapters = workspace.chapters as Array<{
      id: string;
      title: string;
      content: string;
    }>;
    return chapters.find((chapter) => chapter.id === identity.chapterId);
  }).toMatchObject({
    title: "切模式前标题",
    content: "切模式前必须保存的最新正文",
  });
});

test("送审会先保存最新正文并回到阅读只读态", async ({ page }) => {
  const identity = await createNovelWithApi(page);
  await openReadingWorkspace(page, identity);
  await enterMinorEdit(page);

  await page.getByPlaceholder("正文内容").fill("送审按钮点击前刚输入的正文");
  await page.getByRole("button", { name: "送审", exact: true }).click();

  await expect(page.getByPlaceholder("章节标题")).toHaveCount(0);
  await expect(page.getByPlaceholder("正文内容")).toHaveCount(0);
  await expect(page.getByText("章节正在审核中，请先退回草稿后再编辑。")).toBeVisible();
  await expect(page.getByText("送审按钮点击前刚输入的正文", { exact: true })).toBeVisible();
  await expect.poll(async () => {
    const workspace = await readWorkspace(page, identity.novelId);
    const chapters = workspace.chapters as Array<{
      id: string;
      content: string;
      status: string;
    }>;
    return chapters.find((chapter) => chapter.id === identity.chapterId);
  }).toMatchObject({
    content: "送审按钮点击前刚输入的正文",
    status: "review",
  });
});

test("自动保存失败会保留正文并显示可重试状态", async ({ page }) => {
  const identity = await createNovelWithApi(page);
  await openReadingWorkspace(page, identity);
  await enterMinorEdit(page);
  await page.route(`**/api/v1/chapters/${identity.chapterId}`, async (route) => {
    if (route.request().method() !== "PATCH") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ code: "TEST_SAVE_FAILED", message: "模拟保存失败" }),
    });
  });

  const editor = page.getByPlaceholder("正文内容");
  await editor.fill("网络失败时仍留在输入框里的正文");

  await expect(page.getByText("保存失败")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("button", { name: "重试保存" })).toBeVisible();
  await expect(editor).toHaveValue("网络失败时仍留在输入框里的正文");
  await expect(page.getByText("已保存", { exact: true })).toHaveCount(0);
});
