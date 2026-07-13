import { expect, test } from "@playwright/test";

import { createNovelWithApi, openWorkspace, readWorkspace } from "./helpers";

test("用户可以运行质量检查并查看模拟模型零扣费摘要", async ({ page }) => {
  const identity = await createNovelWithApi(page);
  await openWorkspace(page, identity);

  await page.getByPlaceholder("正文内容").fill("用于一致性终检的完整章节正文。");
  await expect(page.getByText("已自动保存")).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "送审", exact: true }).click();
  await page.getByRole("button", { name: /^一致性终检/ }).click();
  await page.getByRole("button", { name: "执行", exact: true }).click();
  await expect.poll(async () => {
    const workspace = await readWorkspace(page, identity.novelId);
    const chapters = workspace.chapters as Array<{
      id: string;
      qualityChecks: Array<{ type: string; status: string }>;
    }>;
    return chapters
      .find((chapter) => chapter.id === identity.chapterId)
      ?.qualityChecks.find((check) => check.type === "consistency")
      ?.status;
  }, { timeout: 60_000 }).toBe("completed");

  await page.reload();
  await page.getByRole("button", { name: /^一致性终检/ }).click();
  await expect(page.locator(".chapter-check-status.completed")).toHaveText("完成");

  await page.goto("/billing");
  await expect(page.getByText(/1000/).first()).toBeVisible();
  const usage = await page.request.get("/api/v1/billing/usage");
  expect(usage.ok()).toBeTruthy();
  const body = (await usage.json()) as {
    totalUsage: { totalTokens: number | string };
  };
  expect(Number(body.totalUsage.totalTokens)).toBe(0);
});
