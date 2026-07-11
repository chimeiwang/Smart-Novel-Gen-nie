import { expect, test } from "@playwright/test";

import { createNovelWithApi, openWorkspace, registerWithApi } from "./helpers";

test("用户可以维护设定、大纲、参考资料和文风画像", async ({ page }) => {
  await registerWithApi(page, "knowledge");
  const identity = await createNovelWithApi(page);
  await openWorkspace(page, identity);

  await page.getByRole("button", { name: "设定", exact: true }).first().click();
  await page.getByRole("button", { name: "+ 新增设定" }).click();
  await page.getByPlaceholder("姓名").fill("端到端角色");
  await page.getByRole("button", { name: "新增设定", exact: true }).click();
  await expect(page.getByText("端到端角色")).toBeVisible();

  await page.getByRole("button", { name: "大纲", exact: true }).first().click();
  await page.getByPlaceholder(/主角从第一卷离开故乡/).fill("端到端总纲：主角完成一次关键选择。");
  await page.getByRole("button", { name: "保存总纲" }).click();
  await expect(page.getByText("总纲已保存")).toBeVisible();
  await page.getByRole("button", { name: "关闭" }).click();

  await page.getByRole("button", { name: "资料", exact: true }).first().click();
  await page.getByPlaceholder("资料标题").fill("端到端资料");
  await page.getByPlaceholder("资料内容").fill("完整参考资料内容，不允许静默截断。");
  await page.getByRole("button", { name: "新增参考资料" }).click();
  await expect(page.getByText("端到端资料")).toBeVisible();

  await page.goto("/styles");
  await page.getByPlaceholder("文风名称").fill("端到端文风");
  await page.getByRole("button", { name: "创建", exact: true }).click();
  await expect(page.getByText("端到端文风")).toBeVisible();
  await page.getByRole("button", { name: "展开" }).first().click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "e2e-style.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("这是一段用于文风画像的完整中文参考正文。".repeat(20)),
  });
  await expect(page.getByText("e2e-style.txt")).toBeVisible();
  await page.getByRole("button", { name: "生成画像" }).click();
  await expect(page.getByText("已完成").first()).toBeVisible({ timeout: 60_000 });
});
