import { expect, test } from "@playwright/test";

import { readWorkspace } from "./helpers";

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
  await expect(page.getByText("已自动保存")).toBeVisible({ timeout: 20_000 });

  const novelId = new URL(page.url()).pathname.split("/").pop();
  expect(novelId).toBeTruthy();
  const workspace = await readWorkspace(page, novelId!);
  const chapters = workspace.chapters as Array<{ title: string; content: string }>;
  expect(chapters[0]).toMatchObject({
    title: "端到端第一章",
    content: "这是通过浏览器输入并自动保存的完整章节正文。",
  });
});
