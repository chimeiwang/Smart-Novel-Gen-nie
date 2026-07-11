import { expect, type APIResponse, type Page } from "@playwright/test";

export const E2E_PASSWORD = "e2e-pass-123";

type NovelIdentity = {
  novelId: string;
  chapterId: string;
};

export function uniqueUsername(prefix: string): string {
  const suffix = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
  return `${prefix}${suffix}`.slice(0, 32);
}

export async function registerWithApi(page: Page, prefix = "e2e"): Promise<string> {
  const username = uniqueUsername(prefix);
  const response = await page.request.post("/api/v1/auth/register", {
    data: {
      username,
      password: E2E_PASSWORD,
      confirmPassword: E2E_PASSWORD,
    },
  });
  await expectApiOk(response, "注册测试用户");
  return username;
}

export async function createNovelWithApi(
  page: Page,
  name = `端到端小说-${Date.now()}`,
): Promise<NovelIdentity> {
  const response = await page.request.post("/api/v1/novels", {
    data: {
      name,
      summary: "端到端测试项目",
      storyLengthProfile: "short_medium",
      targetTotalWordCount: 50_000,
      genre: "测试",
      protagonist: "测试主角",
      coreSellingPoint: "验证完整迁移链路",
      readerPromise: "所有关键流程可恢复",
      firstChapterGoal: "完成端到端验证",
    },
  });
  await expectApiOk(response, "创建测试小说");
  return (await response.json()) as NovelIdentity;
}

export async function readWorkspace(page: Page, novelId: string): Promise<Record<string, unknown>> {
  const response = await page.request.get(`/api/v1/novels/${novelId}/workspace`);
  await expectApiOk(response, "读取工作区");
  return (await response.json()) as Record<string, unknown>;
}

export async function expectApiOk(
  response: APIResponse,
  action: string,
): Promise<void> {
  if (!response.ok()) {
    throw new Error(`${action}失败：${response.status()} ${await response.text()}`);
  }
}

export async function openWorkspace(page: Page, identity: NovelIdentity): Promise<void> {
  await page.goto(`/workspace/${identity.novelId}?chapterId=${identity.chapterId}`);
  await expect(page.getByPlaceholder("章节标题")).toBeVisible();
}
