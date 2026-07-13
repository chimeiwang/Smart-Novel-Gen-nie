import { expect, test } from "@playwright/test";

import {
  createNovelWithApi,
  openWorkspace,
  prepareWritingOutlineWithApi,
  readWorkspace,
} from "./helpers";

test("模拟模型可以完成写作会话和草案应用", async ({ page }) => {
  const identity = await createNovelWithApi(page);
  await prepareWritingOutlineWithApi(page, identity);
  await openWorkspace(page, identity);

  await page.getByRole("button", { name: /生成正文/ }).click();

  await expect(page.getByRole("button", { name: "应用到项目" }).first()).toBeVisible({
    timeout: 60_000,
  });
  await page.getByRole("button", { name: "应用到项目" }).first().click();
  await expect.poll(async () => {
    const workspace = await readWorkspace(page, identity.novelId);
    const chapters = workspace.chapters as Array<{ id: string; content: string }>;
    return chapters.find((chapter) => chapter.id === identity.chapterId)?.content;
  }, { timeout: 30_000 }).toContain("模拟模型生成的完整章节正文");
});

test("用户可以丢弃待确认草案", async ({ page }) => {
  const identity = await createNovelWithApi(page);
  await prepareWritingOutlineWithApi(page, identity);
  await openWorkspace(page, identity);
  await page.getByRole("button", { name: /生成正文/ }).click();
  await expect(page.getByRole("button", { name: "丢弃变更" }).first()).toBeVisible({
    timeout: 60_000,
  });
  await page.getByRole("button", { name: "丢弃变更" }).first().click();
  await expect(page.getByRole("button", { name: "待确认 0" })).toBeVisible();

  const workspace = await readWorkspace(page, identity.novelId);
  const chapters = workspace.chapters as Array<{ id: string; content: string }>;
  expect(chapters.find((chapter) => chapter.id === identity.chapterId)?.content).toBe("");
});
