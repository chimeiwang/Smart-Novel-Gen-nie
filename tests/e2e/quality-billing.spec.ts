import { expect, test } from "@playwright/test";

import { createNovelWithApi, openWorkspace, registerWithApi } from "./helpers";

test("用户可以运行质量检查并查看模拟模型零扣费摘要", async ({ page }) => {
  await registerWithApi(page, "quality");
  const identity = await createNovelWithApi(page);
  await openWorkspace(page, identity);

  await page.getByPlaceholder("正文内容").fill("用于一致性终检的完整章节正文。");
  await expect(page.getByText("已自动保存")).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "送审", exact: true }).click();
  await page.getByRole("button", { name: /一致性终检/ }).click();
  await page.getByRole("button", { name: "执行", exact: true }).click();
  await expect(page.getByText("已完成").first()).toBeVisible({ timeout: 60_000 });

  await page.goto("/billing");
  await expect(page.getByText(/1000/).first()).toBeVisible();
  const summary = await page.request.get("/api/v1/billing/summary");
  expect(summary.ok()).toBeTruthy();
  const body = (await summary.json()) as { totalTokens: number | string };
  expect(Number(body.totalTokens)).toBe(0);
});
