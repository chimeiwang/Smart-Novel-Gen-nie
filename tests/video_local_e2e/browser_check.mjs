import fs from "node:fs/promises";
import process from "node:process";

import { chromium } from "playwright";

const [inputPath, checkpoint, screenshotPath] = process.argv.slice(2);
if (!inputPath || !["a", "b", "c"].includes(checkpoint) || !screenshotPath) {
  throw new Error("用法：browser_check.mjs <private-input.json> <a|b|c> <screenshot.png>");
}

const input = JSON.parse(await fs.readFile(inputPath, "utf8"));
const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await chromium.launch({ headless: true, executablePath: chrome });
const context = await browser.newContext({
  locale: "zh-CN",
  viewport: { width: 1600, height: 1050 },
});
const page = await context.newPage();
const pageErrors = [];
page.on("pageerror", (error) => pageErrors.push(error.message));

const waitForFormValue = async (value) => {
  await page.waitForFunction(
    (expected) =>
      [...document.querySelectorAll("input, textarea")].some(
        (element) => element.value === expected,
      ),
    value,
    { timeout: 60_000 },
  );
};

try {
  const login = await context.request.post(`${input.webUrl}/api/v1/auth/login`, {
    data: { username: input.username, password: input.password },
  });
  if (login.status() !== 200) {
    throw new Error(`浏览器上下文登录失败：HTTP ${login.status()}`);
  }

  if (checkpoint === "a") {
    await page.addInitScript(
      ({ episodeId, baselineId, taskId }) => {
        localStorage.setItem(
          `inkforge:episode-export-tasks:${episodeId}:${baselineId}`,
          JSON.stringify([taskId]),
        );
      },
      {
        episodeId: input.episodeAId,
        baselineId: input.baselineB1Id,
        taskId: input.exportTaskId,
      },
    );
  }

  const episodeId = checkpoint === "a" ? input.episodeAId : input.episodeBId;
  const surface = checkpoint === "a" ? "production" : "script";
  const url = new URL(`/workspace/${encodeURIComponent(input.novelId)}`, input.webUrl);
  url.searchParams.set("view", "video");
  url.searchParams.set("projectId", input.projectId);
  url.searchParams.set("episodeId", episodeId);
  url.searchParams.set("surface", surface);
  await page.goto(url.toString(), { waitUntil: "domcontentloaded", timeout: 60_000 });
  await page.getByRole("heading", { name: "剧集制作", exact: true }).waitFor({ timeout: 60_000 });

  if (checkpoint === "a") {
    await page.getByRole("heading", { name: "雨夜交信", exact: true }).waitFor();
    await page.getByText("隔离模拟", { exact: true }).first().waitFor();
    await page.getByRole("button", { name: "粗剪、声音与交付", exact: true }).click();
    await page.getByRole("heading", { name: "基础粗剪", exact: true }).waitFor({ timeout: 60_000 });
    await page.getByRole("heading", { name: "声音与字幕", exact: true }).waitFor();
    await page.getByRole("heading", { name: "整集交付", exact: true }).waitFor();
    const delivered = page.getByText("交付已归档", { exact: true });
    await delivered.waitFor({ timeout: 60_000 });
    if ((await page.locator(".episode-export-history video").count()) !== 1) {
      throw new Error("场景 A 没有恢复一份可播放的精确交付记录");
    }
    await page
      .locator('[aria-label="当前版本组合"]')
      .getByText("已有", { exact: true })
      .waitFor();
    await delivered.scrollIntoViewIfNeeded();
  } else if (checkpoint === "b") {
    await page.getByRole("heading", { name: "拆信", exact: true }).waitFor();
    await waitForFormValue("顾晚拆信");
    await waitForFormValue("三日前回忆");
    await page.getByText("顾晚在开信场必须已经持有第一集交来的信。", { exact: true }).waitFor();
    await page.getByRole("button", { name: "分镜与制作", exact: true }).click();
    await page.getByText(/当前没有待处理的持久化报告/).waitFor();
    await page.getByRole("button", { name: "剧本", exact: true }).click();
    const dependency = page.getByText(
      "顾晚在开信场必须已经持有第一集交来的信。",
      { exact: true },
    );
    await dependency.waitFor();
    await dependency.scrollIntoViewIfNeeded();
  } else {
    await page.getByRole("heading", { name: "拆信", exact: true }).waitFor();
    await waitForFormValue("三日前回忆");
    await page.getByRole("button", { name: "分镜与制作", exact: true }).click();
    const impactItems = page.locator(".episode-impact-items article");
    await impactItems.first().waitFor({ timeout: 60_000 });
    if ((await impactItems.count()) !== 1) {
      throw new Error("场景 C 的直接影响项不是精确的一项");
    }
    await impactItems.getByText(/原状态：顾晚已经接过沈砚的信/).waitFor();
    await impactItems.getByText(/新状态：沈砚已经收回信/).waitFor();
    if ((await impactItems.getByText(/三日前/).count()) !== 0) {
      throw new Error("场景 C 把独立的三日前回忆误列入了直接影响");
    }
    await impactItems.first().scrollIntoViewIfNeeded();
  }

  if (pageErrors.length) {
    throw new Error(`页面运行错误：${pageErrors.join("；")}`);
  }
  await page.screenshot({ path: screenshotPath, fullPage: true });
  process.stdout.write(
    `${JSON.stringify({ checkpoint, url: page.url(), screenshot: screenshotPath, visible: true })}\n`,
  );
} finally {
  await context.close();
  await browser.close();
}
