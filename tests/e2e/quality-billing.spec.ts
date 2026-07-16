import { expect, test } from "@playwright/test";

import {
  createNovelWithApi,
  enterMinorEdit,
  openReadingWorkspace,
  readWorkspace,
  seedInvalidQualityCheck,
} from "./helpers";

test.use({ viewport: { width: 1440, height: 900 } });

test("用户可以运行质量检查并查看模拟模型零扣费摘要", async ({ page }) => {
  const usageBeforeResponse = await page.request.get("/api/v1/billing/usage");
  expect(usageBeforeResponse.ok()).toBeTruthy();
  const usageBefore = (await usageBeforeResponse.json()) as {
    totalUsage: { totalTokens: number | string };
  };
  const identity = await createNovelWithApi(page);
  await openReadingWorkspace(page, identity);
  await enterMinorEdit(page);

  await page.getByPlaceholder("正文内容").fill("用于一致性终检的完整章节正文。");
  await expect(page.getByText("已保存", { exact: true })).toBeVisible({ timeout: 20_000 });
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

  await expect(page.locator(".chapter-check-status.completed")).toHaveText("完成");

  await page.goto("/billing");
  await expect(page.getByText(/1000/).first()).toBeVisible();
  const usage = await page.request.get("/api/v1/billing/usage");
  expect(usage.ok()).toBeTruthy();
  const body = (await usage.json()) as {
    totalUsage: { totalTokens: number | string };
  };
  expect(
    Number(body.totalUsage.totalTokens) - Number(usageBefore.totalUsage.totalTokens),
  ).toBe(0);
});

test("无效终检在阅读与 AI 创作中都保持待处理并阻止完成", async ({ page }) => {
  const identity = await createNovelWithApi(page);
  await openReadingWorkspace(page, identity);
  await enterMinorEdit(page);

  await page.getByPlaceholder("正文内容").fill("用于验证历史无效终检门禁的完整章节正文。");
  await expect(page.getByText("已保存", { exact: true })).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "送审", exact: true }).click();

  let checkId: string | undefined;
  await expect.poll(async () => {
    const workspace = await readWorkspace(page, identity.novelId);
    const chapters = workspace.chapters as Array<{
      id: string;
      qualityChecks: Array<{ id: string; type: string }>;
    }>;
    checkId = chapters
      .find((chapter) => chapter.id === identity.chapterId)
      ?.qualityChecks.find((check) => check.type === "consistency")
      ?.id;
    return checkId;
  }).not.toBeUndefined();
  await seedInvalidQualityCheck(checkId!);

  await page.goto(
    `/workspace/${identity.novelId}?chapterId=${identity.chapterId}&view=reading`,
  );
  await page.getByRole("button", { name: /^一致性终检/ }).click();
  await expect(page.locator(".chapter-check-status.invalid")).toHaveText("结果无效");
  await expect(page.getByRole("button", { name: "标记完成", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "关闭", exact: true }).click();

  await page.getByRole("button", { name: "AI 创作", exact: true }).click();
  await expect(page.getByText("待处理终检：1", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /预检一致性/ })).toBeVisible();
});
