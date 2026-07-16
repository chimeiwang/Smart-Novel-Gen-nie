import { expect, test } from "@playwright/test";

import { createNovelWithApi, openWorkspace } from "./helpers";

test.use({ viewport: { width: 1440, height: 900 } });

test("创作资料按分组加载，失败可重试并可编辑设定、大纲和参考资料", async ({ page }) => {
  const identity = await createNovelWithApi(page);
  let loreAttempts = 0;
  let planningRequests = 0;
  let resourceRequests = 0;
  await page.route(`**/api/v1/novels/${identity.novelId}/workspace/lore`, async (route) => {
    loreAttempts += 1;
    if (loreAttempts === 1) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ code: "TEST_LORE_FAILED", message: "模拟设定加载失败" }),
      });
      return;
    }
    await route.continue();
  });
  await page.route(`**/api/v1/novels/${identity.novelId}/workspace/planning`, async (route) => {
    planningRequests += 1;
    await route.continue();
  });
  await page.route(`**/api/v1/novels/${identity.novelId}/workspace/resources`, async (route) => {
    resourceRequests += 1;
    await route.continue();
  });
  await openWorkspace(page, identity);

  expect(loreAttempts).toBe(0);
  expect(planningRequests).toBe(0);
  expect(resourceRequests).toBe(0);

  await page.getByRole("button", { name: "创作资料", exact: true }).click();
  await expect(page.getByRole("button", { name: "重试", exact: true })).toBeVisible();
  expect(loreAttempts).toBe(1);
  expect(planningRequests).toBe(0);
  expect(resourceRequests).toBe(0);

  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect(page.getByRole("button", { name: "+ 新增设定" })).toBeVisible();
  expect(loreAttempts).toBe(2);
  await page.getByRole("button", { name: "+ 新增设定" }).click();
  await page.getByPlaceholder("姓名").fill("端到端角色");
  await page.getByRole("button", { name: "新增设定", exact: true }).click();
  await expect(page.getByText("端到端角色")).toBeVisible();

  await page.getByRole("button", { name: "大纲", exact: true }).click();
  await page.getByPlaceholder(/主角从第一卷离开故乡/).fill("端到端总纲：主角完成一次关键选择。");
  await page.getByRole("button", { name: "保存总纲" }).click();
  await expect.poll(async () => {
    const response = await page.request.get(
      `/api/v1/novels/${identity.novelId}/workspace/planning`,
    );
    expect(response.ok()).toBe(true);
    const planning = (await response.json()) as { outline: { content: string } | null };
    return planning.outline?.content;
  }).toBe("端到端总纲：主角完成一次关键选择。");
  expect(planningRequests).toBeGreaterThan(0);
  expect(resourceRequests).toBe(0);

  await page.getByRole("button", { name: "参考资料", exact: true }).click();
  await page.getByPlaceholder("资料标题").fill("端到端资料");
  await page.getByPlaceholder("资料内容").fill("完整参考资料内容，不允许静默截断。");
  await page.getByRole("button", { name: "新增参考资料" }).click();
  await expect(page.getByText("端到端资料")).toBeVisible();
  expect(resourceRequests).toBeGreaterThan(0);

  await page.goto("/styles");
  const styleName = `端到端文风-${Date.now()}`;
  await page.getByPlaceholder("文风名称").fill(styleName);
  await page.getByRole("button", { name: "创建", exact: true }).click();
  await expect(page.getByText(styleName, { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "收起" }).first()).toBeVisible();
  await expect(page.locator('input[type="file"]')).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles({
    name: "e2e-style.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("这是一段用于文风画像的完整中文参考正文。".repeat(20)),
  });
  await expect(page.getByText("e2e-style.txt")).toBeVisible();
  await page.getByRole("button", { name: "生成画像" }).click();
  await expect(page.getByText("已完成").first()).toBeVisible({ timeout: 60_000 });
});
