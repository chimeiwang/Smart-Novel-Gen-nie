import { expect, test } from "@playwright/test";

import {
  createNovelWithApi,
  openWorkspace,
  prepareWritingOutlineWithApi,
  readWorkspace,
} from "./helpers";

test("模拟模型可以完成写作会话和草案应用", async ({ page }) => {
  const identity = await createNovelWithApi(page);
  await prepareWritingOutlineWithApi(page, identity);
  await openWorkspace(page, identity);

  await page.getByRole("button", { name: /生成正文/ }).click();

  await expect(page.getByRole("button", { name: "应用到项目" }).first()).toBeVisible({
    timeout: 60_000,
  });

  const sessionsResponse = await page.request.get(
    `/api/v1/writing/sessions?novelId=${identity.novelId}&chapterId=${identity.chapterId}`,
  );
  expect(sessionsResponse.ok()).toBe(true);
  const sessions = (await sessionsResponse.json()) as Array<{ id: string }>;
  expect(sessions).toHaveLength(1);
  const sessionResponse = await page.request.get(`/api/v1/writing/sessions/${sessions[0].id}`);
  expect(sessionResponse.ok()).toBe(true);
  const session = (await sessionResponse.json()) as {
    messages: Array<{ role: string; content: string }>;
  };
  expect(session.messages.some((message) => message.role === "user")).toBe(true);

  await page.reload();
  await page.getByRole("button", { name: /会话列表/ }).click();
  await page.getByText("未命名会话", { exact: true }).click();
  await expect(page.getByRole("button", { name: "应用到项目" }).first()).toBeVisible({
    timeout: 30_000,
  });
  const workspaceBeforeApply = await readWorkspace(page, identity.novelId);
  const chaptersBeforeApply = workspaceBeforeApply.chapters as Array<{
    id: string;
    content: string;
  }>;
  expect(
    chaptersBeforeApply.find((chapter) => chapter.id === identity.chapterId)?.content,
  ).toBe("");

  await page.getByRole("button", { name: "应用到项目" }).first().click();
  await expect.poll(async () => {
    const workspace = await readWorkspace(page, identity.novelId);
    const chapters = workspace.chapters as Array<{ id: string; content: string }>;
    return chapters.find((chapter) => chapter.id === identity.chapterId)?.content;
  }, { timeout: 30_000 }).toContain("模拟模型生成的完整章节正文");

  await page.reload();
  const completedSessionResponse = await page.request.get(
    `/api/v1/writing/sessions/${sessions[0].id}`,
  );
  expect(completedSessionResponse.ok()).toBe(true);
  const completedSession = (await completedSessionResponse.json()) as {
    currentTask: null;
    lastTask: { phase: string } | null;
  };
  expect(completedSession.currentTask).toBeNull();
  expect(completedSession.lastTask?.phase).toBe("completed");
});

test("用户可以丢弃待确认草案", async ({ page }) => {
  const identity = await createNovelWithApi(page);
  await prepareWritingOutlineWithApi(page, identity);
  await openWorkspace(page, identity);
  await page.getByRole("button", { name: /生成正文/ }).click();
  await expect(page.getByRole("button", { name: "丢弃变更" }).first()).toBeVisible({
    timeout: 60_000,
  });
  await page.getByRole("button", { name: "丢弃变更" }).first().click();
  await expect(page.getByRole("button", { name: "待确认 0" })).toBeVisible();

  await page.reload();
  const sessionsResponse = await page.request.get(
    `/api/v1/writing/sessions?novelId=${identity.novelId}&chapterId=${identity.chapterId}`,
  );
  const sessions = (await sessionsResponse.json()) as Array<{ id: string }>;
  const sessionResponse = await page.request.get(`/api/v1/writing/sessions/${sessions[0].id}`);
  const session = (await sessionResponse.json()) as {
    currentTask: null;
    lastTask: { phase: string } | null;
  };
  expect(session.currentTask).toBeNull();
  expect(session.lastTask?.phase).toBe("completed");

  const workspace = await readWorkspace(page, identity.novelId);
  const chapters = workspace.chapters as Array<{ id: string; content: string }>;
  expect(chapters.find((chapter) => chapter.id === identity.chapterId)?.content).toBe("");
});

test("普通问答完成后可以恢复双方消息", async ({ page }) => {
  const identity = await createNovelWithApi(page);
  await openWorkspace(page, identity);

  const question = "开始写这一章前，我应该先准备什么？";
  await page.getByPlaceholder("输入消息...（@ 邀请助手）").fill(question);
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("模拟模型已完成本轮处理。", { exact: true })).toBeVisible({
    timeout: 60_000,
  });

  await page.reload();
  await page.getByRole("button", { name: /会话列表/ }).click();
  await page.getByText("未命名会话", { exact: true }).click();
  await expect(page.getByText(question, { exact: true })).toBeVisible();
  await expect(page.getByText("模拟模型已完成本轮处理。", { exact: true })).toBeVisible();

  const sessionsResponse = await page.request.get(
    `/api/v1/writing/sessions?novelId=${identity.novelId}&chapterId=${identity.chapterId}`,
  );
  expect(sessionsResponse.ok()).toBe(true);
  const sessions = (await sessionsResponse.json()) as Array<{ id: string }>;
  const sessionResponse = await page.request.get(`/api/v1/writing/sessions/${sessions[0].id}`);
  const session = (await sessionResponse.json()) as {
    messages: Array<{ role: string; content: string }>;
  };
  expect(session.messages.map((message) => message.role)).toEqual(["user", "agent"]);
});
