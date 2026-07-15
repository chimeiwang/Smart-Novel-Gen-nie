import { expect, test } from "@playwright/test";

import {
  createNovelWithApi,
  expectApiOk,
  openWorkspace,
  readWorkspace,
} from "./helpers";

test("用户可以创建小说并自动保存章节", async ({ page }) => {
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "新建小说", exact: true }).click();

  const novelName = `浏览器创建-${Date.now()}`;
  await page.getByLabel("小说名称").fill(novelName);
  await page.getByRole("button", { name: /中短篇/ }).click();
  await page.getByLabel("作品简介").fill("浏览器端到端创建流程");
  await page.locator("form").getByRole("button", { name: "新建小说", exact: true }).click();
  await expect(page).toHaveURL(/\/workspace\/[^?]+/);

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

test("快速输入后切换章节会先保存最新正文", async ({ page }) => {
  const identity = await createNovelWithApi(page);
  const createResponse = await page.request.post(
    `/api/v1/novels/${identity.novelId}/chapters`,
    { data: {} },
  );
  await expectApiOk(createResponse, "创建第二章");
  const secondChapter = (await createResponse.json()) as {
    chapter: { id: string; title: string };
  };
  await openWorkspace(page, identity);

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

test("送审会先保存最新正文并把编辑器切为只读", async ({ page }) => {
  const identity = await createNovelWithApi(page);
  await openWorkspace(page, identity);

  await page.getByPlaceholder("正文内容").fill("送审按钮点击前刚输入的正文");
  await page.getByRole("button", { name: "送审", exact: true }).click();

  await expect(page.getByPlaceholder("章节标题")).not.toBeEditable();
  await expect(page.getByPlaceholder("正文内容")).not.toBeEditable();
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
  await openWorkspace(page, identity);
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
