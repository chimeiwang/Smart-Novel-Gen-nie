import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("工作区保留统一三栏并按需挂载视频制作台", async () => {
  const shellUrl = new URL("../workspace-shell.tsx", import.meta.url);
  const source = await readFile(shellUrl, "utf8");

  assert.match(source, /"章节"/);
  assert.match(source, /"创作资料"/);
  assert.match(source, /history\.replaceState/);
  assert.match(source, /<SmartWritingPanel/);
  assert.match(source, /<ChapterEditor/);
  assert.match(source, /<LibraryPane/);
  assert.match(source, /<LibraryNavigation/);
  assert.match(source, /workspace-left-navigation/);
  assert.match(source, /workspace-primary-switcher/);
  assert.match(source, /"章节"/);
  assert.match(source, /"创作资料"/);
  assert.match(source, /"视频制作"/);
  assert.doesNotMatch(source, /workspace-navigation-root/);
  assert.doesNotMatch(source, /workspace-chapter-mode-switcher/);
  assert.doesNotMatch(source, />AI 创作</);
  assert.doesNotMatch(source, />阅读与小修</);
  assert.match(source, /workspace-collaboration-dock/);
  assert.match(source, /showNavigation=\{false\}/);
  assert.doesNotMatch(source, /workspace-view-switcher/);
  assert.doesNotMatch(source, /key=\{activeView\}/);
  assert.doesNotMatch(source, /workspace-review-rail/);
  assert.match(source, /flushActiveChapterSave/);
  assert.match(source, /activeSection/);
  assert.match(
    source,
    /activeSection === "video" \? \([\s\S]{0,160}<section className="workspace-pane workspace-video-pane">/,
  );
  assert.equal(source.match(/<VideoWorkspace/g)?.length, 1);
  assert.doesNotMatch(source, /SidebarTabs|showChapters|activeView/);
  const librarySelectionBody = source.match(/const selectLibraryItem = async[\s\S]*?\n  \};/)?.[0] ?? "";
  assert.match(librarySelectionBody, /await flushActiveChapterSave\(\)/);
  assert.match(librarySelectionBody, /setActiveLibraryItem\(item\)/);
  assert.match(librarySelectionBody, /setLibraryDialogOpen\(true\)/);
  assert.match(librarySelectionBody, /catch \(error\)[\s\S]*setViewError\(formatWorkspaceViewSaveError\(error\)\)/);
  assert.match(
    source,
    /countUnhandledQualityChecks\([\s\S]{0,100}visibleCurrentChapter\.qualityChecks\.filter/,
  );
  assert.doesNotMatch(source, /check\.status === "pending" \|\| check\.status === "failed"/);
});

test("中短篇作品只进入简化写作台且没有视频入口", async () => {
  const shellUrl = new URL("../workspace-shell.tsx", import.meta.url);
  const source = (await readFile(shellUrl, "utf8")).replaceAll("\r\n", "\n");

  assert.match(source, /novel\.storyLengthProfile === "short_medium"/);
  assert.match(source, /<ShortMediumWorkspace/);
  assert.match(source, /targetTotalWordCount/);
  const shortBranchStart = source.indexOf('if (novel.storyLengthProfile === "short_medium")');
  const shortBranchEnd = source.indexOf("\n\n  return (", shortBranchStart);
  const shortBranch = source.slice(shortBranchStart, shortBranchEnd);
  assert.doesNotMatch(shortBranch, /VideoWorkspace|视频制作/);
  assert.match(source, /resolveWorkspaceViewForProfile/);
  assert.match(source, /\["chapters", "library", "video"\]/);
});

test("视频视图保留章节上下文并隐藏聊天栏", async () => {
  const cssUrl = new URL("../../../app/globals.css", import.meta.url);
  const source = await readFile(cssUrl, "utf8");

  assert.match(
    source,
    /\.workspace-shell\[data-section="video"\]\s*\{\s*grid-template-columns:\s*minmax\(220px,\s*280px\)\s+minmax\(0,\s*1fr\)/,
  );
  assert.match(
    source,
    /\.workspace-shell\[data-section="video"\] \.workspace-collaboration-dock\s*\{\s*display:\s*none/,
  );
  assert.doesNotMatch(source, /short-medium-view-switcher/);
});

test("长篇章节编辑器接收完整的章节进展版本来源", async () => {
  const shellUrl = new URL("../workspace-shell.tsx", import.meta.url);
  const source = await readFile(shellUrl, "utf8");

  assert.match(source, /chapterProgress=\{currentChapter\.progress\s*\?\?\s*null\}/);
  assert.doesNotMatch(source, /chapterProgress=\{currentChapter\.progress\?\.content/);
});

test("审核与确认只使用共享弹窗，不再挂载右侧审核栏", async () => {
  const conversationUrl = new URL("../../writing/writing-conversation.tsx", import.meta.url);
  const source = await readFile(conversationUrl, "utf8");

  assert.match(source, /<WorkspaceDialog/);
  assert.match(source, /title="审核与确认"/);
  assert.doesNotMatch(source, /workspace-review-rail/);
  assert.doesNotMatch(source, /getReviewRailHostSnapshot|reviewRailHost|useSyncExternalStore/);
  const openTrayBody = source.match(/const openArtifactTray[\s\S]*?\n  };/)?.[0] ?? "";
  const inspectBody = source.match(/const inspectReviewArtifactFromTray[\s\S]*?\n  }, \[/)?.[0] ?? "";
  assert.doesNotMatch(openTrayBody, /activeReviewArtifactRef|openReviewArtifactModal/);
  assert.match(inspectBody, /setShowArtifactTray\(false\)[\s\S]*openReviewArtifactModal/);
});

test("资料详情与审核弹窗复用同一 WorkspaceDialog 基础壳", async () => {
  const shellUrl = new URL("../workspace-shell.tsx", import.meta.url);
  const conversationUrl = new URL("../../writing/writing-conversation.tsx", import.meta.url);
  const dialogUrl = new URL("../workspace-dialog.tsx", import.meta.url);
  const [shellSource, conversationSource, dialogSource] = await Promise.all([
    readFile(shellUrl, "utf8"),
    readFile(conversationUrl, "utf8"),
    readFile(dialogUrl, "utf8"),
  ]);

  assert.match(shellSource, /<WorkspaceDialog[\s\S]{0,220}variant="library"/);
  assert.match(conversationSource, /<WorkspaceDialog[\s\S]{0,220}variant="review"/);
  assert.match(dialogSource, /createPortal/);
  assert.match(dialogSource, /role="dialog"/);
  assert.match(dialogSource, /document\.body/);
});

test("创作台使用单一任务入口并隐藏 Agent picker", async () => {
  const conversationUrl = new URL("../../writing/writing-conversation.tsx", import.meta.url);
  const source = await readFile(conversationUrl, "utf8");

  assert.match(source, /创作任务/);
  assert.match(source, /历史对话/);
  assert.match(source, /开始新对话/);
  assert.match(source, /系统会自动分配合适的 Agent/);
  assert.doesNotMatch(source, /showAgentPicker|agentPickerActiveIndex|role="listbox"/);
});

test("会话恢复完成前不会把临时 idle 阶段写回服务端", async () => {
  const conversationUrl = new URL("../../writing/writing-conversation.tsx", import.meta.url);
  const source = await readFile(conversationUrl, "utf8");

  assert.match(source, /phasePersistenceReadyRef/);
  assert.match(source, /if \(!phasePersistenceReadyRef\.current\) return/);
  assert.match(source, /requireApiData\(await browserApi\.PATCH/);
});

test("当前会话收到权威终态后重新读取持久化消息但不覆盖终态界面", async () => {
  const conversationUrl = new URL("../../writing/writing-conversation.tsx", import.meta.url);
  const source = await readFile(conversationUrl, "utf8");

  assert.match(source, /preserveWorkspaceState/);
  assert.match(
    source,
    /const loadSessionMessages[\s\S]{0,320}sessionLoadVersionRef\.current \+= 1[\s\S]{0,160}const requestVersion = sessionLoadVersionRef\.current/,
  );
  assert.match(
    source,
    /decision\.kind === "waiting_user"[\s\S]*loadSessionMessages\(scope\.sessionId,\s*\{ preserveWorkspaceState: true \}\)/,
  );
  assert.match(
    source,
    /decision\.kind === "succeeded"[\s\S]*loadSessionMessages\(scope\.sessionId,\s*\{ preserveWorkspaceState: true \}\)/,
  );
  assert.match(
    source,
    /event\.eventType === "completed"[\s\S]*workflowEventRequiresSessionMessageRefresh\(event\)[\s\S]*loadSessionMessages\(scope\.sessionId,\s*\{ preserveWorkspaceState: true \}\)/,
  );
  assert.match(
    source,
    /event\.payload\.artifactId[\s\S]*loadReviewArtifacts\(\)/,
  );
});

test("审核托盘用一次权威摘要列表查询汇总产物并淘汰旧响应", async () => {
  const conversationUrl = new URL("../../writing/writing-conversation.tsx", import.meta.url);
  const source = await readFile(conversationUrl, "utf8");

  assert.match(source, /"\/api\/v1\/review-artifact-summaries"/);
  assert.match(source, /status: "awaiting_user"/);
  assert.doesNotMatch(source, /Promise\.allSettled\(taskIds/);
  assert.match(source, /artifactCollectionVersionRef/);
  assert.match(source, /artifactTrayArtifacts\.map/);
  assert.match(source, /mergeActionableReviewArtifacts/);
});

test("开始新对话不会清空其他会话待审核产物", async () => {
  const conversationUrl = new URL("../../writing/writing-conversation.tsx", import.meta.url);
  const source = await readFile(conversationUrl, "utf8");
  const resetBody = source.match(/const resetSessionContext[\s\S]*?\n  \}, \[/)?.[0] ?? "";

  assert.doesNotMatch(resetBody, /setReviewArtifacts\(\[\]\)/);
});

test("审核托盘中的非当前会话产物也能进入返工流程", async () => {
  const conversationUrl = new URL("../../writing/writing-conversation.tsx", import.meta.url);
  const source = await readFile(conversationUrl, "utf8");
  const cardBody = source.match(/const renderArtifactReviewCard[\s\S]*?const renderArtifactReviewDialog/)?.[0] ?? "";

  assert.match(cardBody, /handleArtifactDecision\(artifact,\s*"revise"/);
});

test("工作区外壳跟随服务端 initialView", async () => {
  const shellUrl = new URL("../workspace-shell.tsx", import.meta.url);
  const source = await readFile(shellUrl, "utf8");

  assert.match(source, /useEffect\([\s\S]*initialView/);
  assert.match(source, /previousInitialViewRef/);
  assert.doesNotMatch(source, /addEventListener\("popstate"/);
  assert.doesNotMatch(source, /activeViewRef|popstateTransitionRef/);
});

test("studio 使用单一宽主画布，窄桌面可滚动降级", async () => {
  const cssUrl = new URL("../../../app/globals.css", import.meta.url);
  const source = await readFile(cssUrl, "utf8");

  assert.doesNotMatch(source, /workspace-shell-main\[data-view="studio"\][\s\S]{0,160}1\.05fr/);
  assert.match(source, /@media \(max-width: 999px\)/);
  assert.match(source, /workspace-page[\s\S]{0,100}overflow: auto/);
});

test("完整桌面在 1280 与 1920 宽度保留三栏并限制阅读宽度", async () => {
  const cssUrl = new URL("../../../app/globals.css", import.meta.url);
  const source = await readFile(cssUrl, "utf8");

  assert.doesNotMatch(source, /\.workspace-page\s*\{[^}]*min-width:\s*1440px/);
  assert.match(
    source,
    /grid-template-columns:\s*minmax\(220px,\s*280px\)\s+minmax\(640px,\s*1fr\)\s+minmax\(380px,\s*440px\)/,
  );
  assert.match(source, /@media \(min-width: 1920px\)/);
  assert.match(source, /chapter-reading-content[\s\S]{0,140}max-width:/);
  assert.match(source, /@media \(max-width: 1439px\)/);
});

test("工作区导航与用户浮层使用不同垂直区域", async () => {
  const cssUrl = new URL("../../../app/globals.css", import.meta.url);
  const menuUrl = new URL("../../auth/user-menu.tsx", import.meta.url);
  const [source, menuSource] = await Promise.all([
    readFile(cssUrl, "utf8"),
    readFile(menuUrl, "utf8"),
  ]);

  assert.doesNotMatch(source, /\.workspace-shell-header[\s\S]{0,220}padding-right:\s*240px/);
  assert.match(menuSource, /top:\s*72/);
  assert.match(menuSource, /Math\.max\(72,/);
  assert.match(source, /\.home-header[\s\S]{0,160}padding-right:\s*240px/);
});

test("编辑器草稿字数同步到章节列表、总字数和智能写作上下文", async () => {
  const shellUrl = new URL("../workspace-shell.tsx", import.meta.url);
  const editorUrl = new URL("../../editor/chapter-editor.tsx", import.meta.url);
  const [shellSource, editorSource] = await Promise.all([
    readFile(shellUrl, "utf8"),
    readFile(editorUrl, "utf8"),
  ]);

  assert.match(shellSource, /visibleChapters/);
  assert.match(shellSource, /onDraftChange=\{updateLiveDraft\}/);
  assert.match(shellSource, /onSaved=\{updateLiveDraft\}/);
  assert.match(editorSource, /wordCount:\s*chapterWordCount/);
});

test("创作台更多按钮不竖排且待确认入口只在有产物时显示", async () => {
  const conversationUrl = new URL("../../writing/writing-conversation.tsx", import.meta.url);
  const cssUrl = new URL("../../writing/writing-conversation.css", import.meta.url);
  const [conversationSource, cssSource] = await Promise.all([
    readFile(conversationUrl, "utf8"),
    readFile(cssUrl, "utf8"),
  ]);

  assert.match(conversationSource, /className="more-menu-button"/);
  assert.match(cssSource, /\.writing-chat \.more-menu-button[\s\S]{0,180}white-space:\s*nowrap/);
  assert.match(
    conversationSource,
    /effectiveAwaitingArtifactCount > 0 \? \([\s\S]{0,220}待确认/,
  );
});

test("窄右栏中的创作任务保持标题在上和两列等宽布局", async () => {
  const conversationUrl = new URL("../../writing/writing-conversation.tsx", import.meta.url);
  const cssUrl = new URL("../../writing/writing-conversation.css", import.meta.url);
  const [conversationSource, cssSource] = await Promise.all([
    readFile(conversationUrl, "utf8"),
    readFile(cssUrl, "utf8"),
  ]);
  const taskPanelRule = cssSource.match(/\.writing-chat \.writing-task-panel\s*\{([^}]*)\}/)?.[1] ?? "";
  const kickerRule = cssSource.match(
    /\.writing-chat \.writing-task-panel \.next-action-kicker\s*\{([^}]*)\}/,
  )?.[1] ?? "";
  const buttonsRule = cssSource.match(
    /\.writing-chat \.writing-task-panel \.next-action-buttons\s*\{([^}]*)\}/,
  )?.[1] ?? "";
  const buttonRule = cssSource.match(
    /\.writing-chat \.writing-task-panel \.next-action-button\s*\{([^}]*)\}/,
  )?.[1] ?? "";

  assert.match(
    conversationSource,
    /className="next-action-panel writing-task-panel"[\s\S]*className="next-action-kicker"[\s\S]*className="next-action-buttons"/,
  );
  assert.match(taskPanelRule, /flex-direction:\s*column/);
  assert.match(taskPanelRule, /align-items:\s*stretch/);
  assert.match(kickerRule, /white-space:\s*nowrap/);
  assert.match(buttonsRule, /display:\s*grid/);
  assert.match(buttonsRule, /grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/);
  assert.match(buttonRule, /min-width:\s*0/);
  assert.match(buttonRule, /width:\s*100%/);
});
