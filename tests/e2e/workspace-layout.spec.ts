import { expect, test, type Locator } from "@playwright/test";

import { createNovelWithApi, openWorkspace } from "./helpers";

async function requireBox(locator: Locator) {
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  return box!;
}

test("统一工作区在 1440 与 1920 宽度下保留三栏并由主画布吸收额外空间", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const identity = await createNovelWithApi(page);
  await openWorkspace(page, identity);

  const navigation = page.locator(".workspace-left-navigation");
  const main = page.locator('.workspace-shell-main[data-view="studio"]');
  const collaboration = page.getByRole("complementary", { name: "聊天协作" });
  const navigation1440 = await requireBox(navigation);
  const main1440 = await requireBox(main);
  const collaboration1440 = await requireBox(collaboration);

  expect(navigation1440.width).toBeGreaterThanOrEqual(220);
  expect(navigation1440.width).toBeLessThanOrEqual(280);
  expect(collaboration1440.width).toBeGreaterThanOrEqual(380);
  expect(collaboration1440.width).toBeLessThanOrEqual(440);
  expect(Math.abs(navigation1440.y - main1440.y)).toBeLessThan(2);
  expect(Math.abs(collaboration1440.y - main1440.y)).toBeLessThan(2);

  await page.getByRole("button", { name: "创作资料", exact: true }).click();
  await expect(page.getByRole("button", { name: "创作资料", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(collaboration).toBeVisible();
  await page.getByRole("button", { name: "章节", exact: true }).click();
  await expect(page.getByRole("button", { name: "章节", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  await page.setViewportSize({ width: 1920, height: 1080 });
  await expect.poll(async () => (await main.boundingBox())?.width ?? 0).toBeGreaterThan(
    main1440.width + 400,
  );
  const navigation1920 = await requireBox(navigation);
  const collaboration1920 = await requireBox(collaboration);
  expect(navigation1920.width).toBeLessThanOrEqual(280);
  expect(collaboration1920.width).toBeLessThanOrEqual(440);
});
