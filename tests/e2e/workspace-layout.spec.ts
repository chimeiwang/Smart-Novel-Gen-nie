import { expect, test, type Locator } from "@playwright/test";

import { createNovelWithApi, openWorkspace } from "./helpers";

async function requireBox(locator: Locator) {
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  return box!;
}

test("1440 与 1920 宽度下保留三栏，额外空间由主画布吸收", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const identity = await createNovelWithApi(page);
  await openWorkspace(page, identity);

  const navigation = page.locator(".workspace-chapter-navigation");
  const main = page.locator('.workspace-shell-main[data-view="studio"]');
  const reviewRail = page.getByRole("complementary", { name: "当前章节审核栏" });
  const navigation1440 = await requireBox(navigation);
  const main1440 = await requireBox(main);
  const review1440 = await requireBox(reviewRail);

  expect(navigation1440.width).toBeGreaterThanOrEqual(240);
  expect(navigation1440.width).toBeLessThanOrEqual(280);
  expect(review1440.width).toBeGreaterThanOrEqual(340);
  expect(review1440.width).toBeLessThanOrEqual(400);
  expect(Math.abs(navigation1440.y - main1440.y)).toBeLessThan(2);
  expect(Math.abs(review1440.y - main1440.y)).toBeLessThan(2);

  await page.getByRole("button", { name: "阅读与小修", exact: true }).click();
  await expect(reviewRail).toBeVisible();
  await page.getByRole("button", { name: "创作资料", exact: true }).click();
  await expect(reviewRail).toBeVisible();
  await page.getByRole("button", { name: "AI 创作", exact: true }).click();
  await expect(page.getByRole("button", { name: "AI 创作", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  await page.setViewportSize({ width: 1920, height: 1080 });
  await expect.poll(async () => (await main.boundingBox())?.width ?? 0).toBeGreaterThan(
    main1440.width + 400,
  );
  const navigation1920 = await requireBox(navigation);
  const review1920 = await requireBox(reviewRail);
  expect(navigation1920.width).toBeLessThanOrEqual(280);
  expect(review1920.width).toBeLessThanOrEqual(400);
});
