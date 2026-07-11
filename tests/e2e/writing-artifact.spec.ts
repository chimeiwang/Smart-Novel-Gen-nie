import { expect, test } from "@playwright/test";

import { createNovelWithApi, openWorkspace, registerWithApi } from "./helpers";

test("模拟模型可以完成写作会话和草案应用", async ({ page }) => {
  await registerWithApi(page, "writing");
  const identity = await createNovelWithApi(page);
  await openWorkspace(page, identity);

  await page.getByRole("button", { name: "智能写作", exact: true }).first().click();
  await page.getByRole("button", { name: "+ 新建会话" }).click();
  await page.getByPlaceholder(/输入消息/).fill("写一章正文");
  await page.getByRole("button", { name: "发送", exact: true }).click();

  await expect(page.getByRole("button", { name: "应用到项目" }).first()).toBeVisible({
    timeout: 60_000,
  });
  await page.getByRole("button", { name: "应用到项目" }).first().click();
  await expect(page.getByText(/已应用/).first()).toBeVisible({ timeout: 30_000 });

  const workspaceResponse = await page.request.get(
    `/api/v1/novels/${identity.novelId}/workspace?chapterId=${identity.chapterId}`,
  );
  expect(workspaceResponse.ok()).toBeTruthy();
  const workspace = (await workspaceResponse.json()) as {
    chapters: Array<{ id: string; content: string }>;
  };
  expect(workspace.chapters.find((chapter) => chapter.id === identity.chapterId)?.content).toContain(
    "模拟模型生成的完整章节正文",
  );
});

test("用户可以丢弃待确认草案", async ({ page }) => {
  await registerWithApi(page, "discard");
  const identity = await createNovelWithApi(page);
  await openWorkspace(page, identity);
  await page.getByRole("button", { name: "智能写作", exact: true }).first().click();
  await page.getByRole("button", { name: "+ 新建会话" }).click();
  await page.getByPlaceholder(/输入消息/).fill("写一章正文");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.getByRole("button", { name: "丢弃变更" }).first()).toBeVisible({
    timeout: 60_000,
  });
  await page.getByRole("button", { name: "丢弃变更" }).first().click();
  await expect(page.getByText(/已丢弃/).first()).toBeVisible({ timeout: 30_000 });
});
