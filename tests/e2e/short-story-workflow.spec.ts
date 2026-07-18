import { expect, test } from "@playwright/test";

import {
  countShortStoryTextLength,
  createShortNovelWithApi,
  createShortStorySessionWithApi,
  decideShortStoryArtifactWithApi,
  expectApiOk,
  readChapterWithApi,
  readShortStoryAggregate,
  readWorkspace,
  startShortStoryOperationWithApi,
  type ShortStoryArtifact,
  type ShortStoryDraftPayload,
  type ShortStoryOutlinePayload,
  waitForShortStoryAggregate,
} from "./helpers";

test.use({ viewport: { width: 1440, height: 900 } });

function requireOutline(artifact: ShortStoryArtifact | null): {
  artifact: ShortStoryArtifact;
  payload: ShortStoryOutlinePayload;
} {
  if (!artifact || artifact.payload.kind !== "outline_draft") {
    throw new Error("中短篇完整大纲尚未生成");
  }
  return { artifact, payload: artifact.payload };
}

function requireDraft(artifact: ShortStoryArtifact | null): {
  artifact: ShortStoryArtifact;
  payload: ShortStoryDraftPayload;
} {
  if (!artifact || artifact.payload.kind !== "chapter_draft") {
    throw new Error("中短篇完整正文尚未生成");
  }
  return { artifact, payload: artifact.payload };
}

function expectCurrentRevisionReviews(artifact: ShortStoryArtifact): void {
  const evaluations = (artifact.evaluations ?? []).filter(
    (evaluation) => evaluation.revision === artifact.revision,
  );
  expect(evaluations).toHaveLength(2);

  const editor = evaluations.find((evaluation) => evaluation.evaluatorAgent === "编辑");
  const validator = evaluations.find((evaluation) => evaluation.evaluatorAgent === "校验");
  expect(editor?.verdict).toBe("pass");
  expect(validator?.verdict).toBe("pass");
  expect(new Date(editor!.createdAt).getTime()).toBeLessThanOrEqual(
    new Date(validator!.createdAt).getTime(),
  );
}

function expectExactlyOneAutomaticRewrite(
  artifact: ShortStoryArtifact,
  payload: ShortStoryDraftPayload,
): void {
  expect(payload.metadata.automaticRewriteCount).toBe(1);
  expect(payload.metadata.generationReason).toBe("automatic_rewrite");
  expectCurrentRevisionReviews(artifact);
}

test("6000 字中短篇可从灵感多次改纲、完整返工并批准为唯一正文", async ({ page }) => {
  test.setTimeout(240_000);

  const revisionApiRequests: string[] = [];
  const draftRevisionApiFailures: string[] = [];
  page.on("request", (request) => {
    if (/\/api\/v1\/review-artifacts\/[^/]+\/revisions(?:\/\d+)?$/u.test(request.url())) {
      revisionApiRequests.push(request.url());
    }
  });
  page.on("response", (response) => {
    if (
      /\/api\/v1\/review-artifacts\/[^/]+\/revisions(?:\/\d+)?$/u.test(response.url())
      && response.status() >= 400
    ) {
      draftRevisionApiFailures.push(`${response.status()} ${response.url()}`);
    }
  });

  await page.goto("/dashboard");
  await page.getByRole("button", { name: "新建小说", exact: true }).click();
  await page.getByRole("button", { name: /^中短篇/ }).click();

  const title = `六千字中短篇-${Date.now()}`;
  const inspiration = "[E2E_AUTO_REWRITE_ONCE] 一个守夜人发现每次敲钟都会让城里一个人被遗忘，结尾他必须决定是否敲最后一次。";
  await page.getByLabel("暂定标题（可选）").fill(title);
  await page.getByLabel("灵感").fill(inspiration);
  await page.getByLabel("目标总字数").fill("6000");
  await page.getByRole("button", { name: "创建并生成大纲", exact: true }).click();

  await expect(page).toHaveURL(/\/workspace\/[^?]+/);
  await expect(page.getByRole("complementary", { name: "中短篇写作流程" })).toBeVisible();
  const novelId = new URL(page.url()).pathname.split("/").pop();
  if (!novelId) throw new Error("创建中短篇后没有取得 novelId");

  const workspace = await readWorkspace(page, novelId);
  const currentChapter = workspace.currentChapter as { id: string; title: string } | null;
  if (!currentChapter) throw new Error("中短篇项目没有唯一正文 Chapter");
  expect(currentChapter.title).toBe("正文");

  const initialAggregate = await waitForShortStoryAggregate(
    page,
    novelId,
    (aggregate) => aggregate.outline?.status === "awaiting_user",
    "等待首版完整大纲交给用户",
  );
  const initialOutline = requireOutline(initialAggregate.outline);
  expect(initialOutline.payload.originalInspiration).toBe(inspiration);
  expect(initialOutline.payload.sections).toHaveLength(3);
  const stableSectionIds = initialOutline.payload.sections.map((section) => section.id);

  const firstOutlineRequest = "只修改第 2 节，让追查遗忘规则的冲突更早爆发。";
  const outlineRequestInput = page.getByPlaceholder("例如：只修改第 3 节，让冲突更早爆发");
  await expect(outlineRequestInput).toBeVisible();
  await outlineRequestInput.fill(firstOutlineRequest);
  await page.getByRole("button", { name: "按要求修改大纲", exact: true }).click();

  const firstRevisionAggregate = await waitForShortStoryAggregate(
    page,
    novelId,
    (aggregate) => Boolean(
      aggregate.outline?.status === "awaiting_user"
      && aggregate.outline.revision > initialOutline.artifact.revision,
    ),
    "等待第一次局部改纲完成",
  );
  const firstRevision = requireOutline(firstRevisionAggregate.outline);
  expect(firstRevision.payload.sections.map((section) => section.id)).toEqual(stableSectionIds);
  expect(firstRevision.payload.changeSummary).toContain("本轮大纲修改");

  const secondOutlineRequest = "保留前两节，只强化第 3 节的最终选择和结局兑现。";
  await expect(page.getByRole("button", { name: "按要求修改大纲", exact: true })).toBeEnabled();
  await outlineRequestInput.fill(secondOutlineRequest);
  await page.getByRole("button", { name: "按要求修改大纲", exact: true }).click();

  const secondRevisionAggregate = await waitForShortStoryAggregate(
    page,
    novelId,
    (aggregate) => Boolean(
      aggregate.outline?.status === "awaiting_user"
      && aggregate.outline.revision > firstRevision.artifact.revision,
    ),
    "等待第二次局部改纲完成",
  );
  const secondRevision = requireOutline(secondRevisionAggregate.outline);
  expect(secondRevision.payload.sections.map((section) => section.id)).toEqual(stableSectionIds);
  expect(secondRevision.payload.sections).toHaveLength(initialOutline.payload.sections.length);

  const writingSessionId = secondRevisionAggregate.workflowSession?.id;
  if (!writingSessionId) throw new Error("中短篇改纲没有关联写作会话");
  const sessionResponse = await page.request.get(`/api/v1/writing/sessions/${writingSessionId}`);
  await expectApiOk(sessionResponse, "读取中短篇改纲会话");
  const session = (await sessionResponse.json()) as {
    messages: Array<{ role: string; content: string }>;
  };
  const userMessages = session.messages
    .filter((message) => message.role === "user")
    .map((message) => message.content);
  expect(userMessages).toContain(firstOutlineRequest);
  expect(userMessages).toContain(secondOutlineRequest);

  await expect(page.getByRole("button", { name: "批准当前大纲", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "批准当前大纲", exact: true }).click();
  await waitForShortStoryAggregate(
    page,
    novelId,
    (aggregate) => aggregate.outline?.status === "applied",
    "等待大纲批准完成",
  );

  await expect(page.getByRole("button", { name: "生成完整初稿", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "生成完整初稿", exact: true }).click();
  const firstDraftAggregate = await waitForShortStoryAggregate(
    page,
    novelId,
    (aggregate) => aggregate.chapterDraft?.status === "awaiting_user",
    "等待 6000 字完整正文和双审核完成",
    120_000,
  );
  const firstDraft = requireDraft(firstDraftAggregate.chapterDraft);
  expect(firstDraft.payload.metadata.targetWordCount).toBe(6_000);
  expect(firstDraft.payload.metadata.actualWordCount).toBe(6_000);
  expect(firstDraft.payload.metadata.sourceOutlineArtifactId).toBe(secondRevision.artifact.id);
  expect(firstDraft.payload.metadata.sourceOutlineRevision).toBe(secondRevision.artifact.revision);
  expect(firstDraft.payload.metadata.targetChapterId).toBe(currentChapter.id);
  expect(countShortStoryTextLength(firstDraft.payload.content)).toBe(6_000);
  expect(firstDraft.payload.content).toContain("【模拟整稿尾部】");
  expect(firstDraft.artifact.revision).toBe(2);
  expectExactlyOneAutomaticRewrite(firstDraft.artifact, firstDraft.payload);

  await page.getByRole("button", { name: "完整大纲", exact: true }).click();
  await page.getByRole("button", { name: "完整正文", exact: true }).click();
  await expect(page.getByText("实际 6000 字", { exact: true })).toBeVisible();
  await expect(page.getByText(/自动返工 \d\/1/, { exact: true })).toBeVisible();
  await expect(page.locator("article.short-story-content")).toContainText("【模拟整稿尾部】");
  await expect(page.getByRole("heading", { name: "编辑审核", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "校验审核", exact: true })).toBeVisible();
  await page.evaluate(() => new Promise<void>((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
  }));
  await expect(page.getByRole("alert").filter({ hasText: "读取草案版本失败" })).toHaveCount(0);
  expect(
    revisionApiRequests.filter((url) => url.includes(`/review-artifacts/${firstDraft.artifact.id}/`)),
  ).toEqual([]);
  expect(draftRevisionApiFailures).toEqual([]);

  const manuscriptRevisionRequest = "保留完整结局，只让开场的敲钟危机更快发生。";
  await page
    .getByPlaceholder("写下新的整稿修改要求，可反复修改，不受自动返工次数限制")
    .fill(manuscriptRevisionRequest);
  await page.getByRole("button", { name: "按要求完整返工", exact: true }).click();
  const revisedDraftAggregate = await waitForShortStoryAggregate(
    page,
    novelId,
    (aggregate) => Boolean(
      aggregate.chapterDraft?.status === "awaiting_user"
      && aggregate.chapterDraft.revision > firstDraft.artifact.revision,
    ),
    "等待用户要求的完整返稿与新一轮双审核完成",
    120_000,
  );
  const revisedDraft = requireDraft(revisedDraftAggregate.chapterDraft);
  expect(revisedDraft.payload.metadata.sourceOutlineRevision).toBe(secondRevision.artifact.revision);
  expect(countShortStoryTextLength(revisedDraft.payload.content)).toBe(6_000);
  expect(revisedDraft.artifact.revision).toBe(firstDraft.artifact.revision + 2);
  expectExactlyOneAutomaticRewrite(revisedDraft.artifact, revisedDraft.payload);

  await expect(page.getByRole("button", { name: "批准并应用正式正文", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "批准并应用正式正文", exact: true }).click();
  await waitForShortStoryAggregate(
    page,
    novelId,
    (aggregate) => aggregate.chapterDraft?.status === "applied",
    "等待完整正文正式应用",
  );

  const appliedChapter = await readChapterWithApi(page, currentChapter.id);
  expect(appliedChapter.title).toBe("正文");
  expect(countShortStoryTextLength(appliedChapter.content)).toBe(6_000);
  expect(appliedChapter.content).toContain("【模拟整稿尾部】");
  expect(appliedChapter.qualityChecks.find((check) => check.type === "consistency")).toMatchObject({
    status: "skipped",
    summary: "已由中短篇全稿审核覆盖",
  });

  const appliedWorkspace = await readWorkspace(page, novelId);
  expect(appliedWorkspace.chapters as unknown[]).toHaveLength(1);
});

test("80000 字边界通过显式 API Operation 一次生成完整正文并正式应用", async ({ page }) => {
  test.setTimeout(180_000);

  const targetWordCount = 80_000;
  const identity = await createShortNovelWithApi(page, targetWordCount);
  const writingSessionId = await createShortStorySessionWithApi(page, identity);
  await startShortStoryOperationWithApi(
    page,
    identity,
    writingSessionId,
    "develop_short_outline",
    targetWordCount,
    "根据原始灵感生成完整中短篇大纲。",
  );

  const outlineAggregate = await waitForShortStoryAggregate(
    page,
    identity.novelId,
    (aggregate) => aggregate.outline?.status === "awaiting_user",
    "等待 80000 字项目的大纲生成",
  );
  const outline = requireOutline(outlineAggregate.outline);
  await decideShortStoryArtifactWithApi(page, outline.artifact, "approve");
  await waitForShortStoryAggregate(
    page,
    identity.novelId,
    (aggregate) => aggregate.outline?.status === "applied",
    "等待 80000 字项目的大纲批准",
  );

  await startShortStoryOperationWithApi(
    page,
    identity,
    writingSessionId,
    "write_short_story",
    targetWordCount,
    "严格按批准大纲一次生成完整 80000 字正文并完成全稿审核。",
  );
  const draftAggregate = await waitForShortStoryAggregate(
    page,
    identity.novelId,
    (aggregate) => aggregate.chapterDraft?.status === "awaiting_user",
    "等待 80000 字完整正文和双审核完成",
    120_000,
  );
  const draft = requireDraft(draftAggregate.chapterDraft);
  expect(draft.payload.metadata.targetWordCount).toBe(targetWordCount);
  expect(draft.payload.metadata.actualWordCount).toBe(targetWordCount);
  expect(draft.payload.metadata.sourceOutlineArtifactId).toBe(outline.artifact.id);
  expect(draft.payload.metadata.sourceOutlineRevision).toBe(outline.artifact.revision);
  expect(draft.payload.metadata.targetChapterId).toBe(identity.chapterId);
  expect(countShortStoryTextLength(draft.payload.content)).toBe(targetWordCount);
  expect(draft.payload.content.endsWith("【模拟整稿尾部】")).toBe(true);
  expect(draft.payload.metadata.automaticRewriteCount).toBe(0);
  expect(draft.payload.metadata.generationReason).toBe("user_request");
  expectCurrentRevisionReviews(draft.artifact);

  await decideShortStoryArtifactWithApi(page, draft.artifact, "approve");
  await waitForShortStoryAggregate(
    page,
    identity.novelId,
    (aggregate) => aggregate.chapterDraft?.status === "applied",
    "等待 80000 字完整正文正式应用",
  );

  const chapter = await readChapterWithApi(page, identity.chapterId);
  expect(chapter.title).toBe("正文");
  expect(countShortStoryTextLength(chapter.content)).toBe(targetWordCount);
  expect(chapter.content.endsWith("【模拟整稿尾部】")).toBe(true);
  expect(chapter.qualityChecks.find((check) => check.type === "consistency")).toMatchObject({
    status: "skipped",
    summary: "已由中短篇全稿审核覆盖",
  });

  const finalWorkspace = await readWorkspace(page, identity.novelId);
  expect(finalWorkspace.chapters as unknown[]).toHaveLength(1);
  const finalAggregate = await readShortStoryAggregate(page, identity.novelId);
  expect(finalAggregate.chapterDraft?.status).toBe("applied");
});
