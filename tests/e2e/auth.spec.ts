import { expect, test } from "@playwright/test";

import { AUTH_STATE_PATH } from "./auth-state";
import { E2E_PASSWORD, uniqueUsername } from "./helpers";

test("用户可以注册、退出并重新登录", async ({ page }) => {
  const username = uniqueUsername("auth");

  await page.goto("/login");
  await page.getByRole("button", { name: "没有账号？注册" }).click();
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码", { exact: true }).fill(E2E_PASSWORD);
  await page.getByLabel("确认密码").fill(E2E_PASSWORD);
  await page.getByRole("button", { name: "注册并登录" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByText("墨铸写作工作台")).toBeVisible();

  await page.getByRole("button", { name: "退出", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill(E2E_PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.context().storageState({ path: AUTH_STATE_PATH });
});
