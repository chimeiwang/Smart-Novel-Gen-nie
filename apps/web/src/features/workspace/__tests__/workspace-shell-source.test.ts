import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("工作区外壳使用章节与创作资料平级分段导航", async () => {
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
  const librarySelectionBody = source.match(/const selectLibraryItem = async[\s\S]*?\n  \};/)?.[0] ?? "";
  assert.match(librarySelectionBody, /await flushActiveChapterSave\(\)/);
  assert.match(librarySelectionBody, /setActiveLibraryItem\(item\)/);
  assert.match(librarySelectionBody, /setLibraryDialogOpen\(true\)/);
  assert.match(librarySelectionBody, /catch \(error\)[\s\S]*setViewError\(formatWorkspaceViewSaveError\(error\)\)/);
  assert.match(source, /countUnhandledQualityChecks\([\s\S]{0,100}currentChapter\.qualityChecks\.filter/);
  assert.doesNotMatch(source, /check\.status === "pending" \|\| check\.status === "failed"/);
});

test("中短篇作品进入简化双文档工作台而不是长篇三栏流程", async () => {
  const shellUrl = new URL("../workspace-shell.tsx", import.meta.url);
  const source = await readFile(shellUrl, "utf8");

  assert.match(source, /novel\.storyLengthProfile === "short_medium"/);
  assert.match(source, /<ShortMediumWorkspace/);
  assert.match(source, /targetTotalWordCount/);
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

test("审核栏汇总多个会话产物并隔离并发失败与旧响应", async () => {
  const conversationUrl = new URL("../../writing/writing-conversation.tsx", import.meta.url);
  const source = await readFile(conversationUrl, "utf8");

  assert.match(source, /Promise\.allSettled/);
  assert.match(source, /artifactCollectionVersionRef/);
  assert.match(source, /reviewRailArtifacts\.map/);
  assert.match(source, /mergeActionableReviewArtifacts/);
});

test("开始新对话不会清空其他会话待审核产物", async () => {
  const conversationUrl = new URL("../../writing/writing-conversation.tsx", import.meta.url);
  const source = await readFile(conversationUrl, "utf8");
  const resetBody = source.match(/const resetSessionContext[\s\S]*?\n  \}, \[/)?.[0] ?? "";

  assert.doesNotMatch(resetBody, /setReviewArtifacts\(\[\]\)/);
});

test("审核栏中的非当前会话产物也能进入返工流程", async () => {
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

test("完整桌面在 1440 与 1920 宽度保留三栏并限制阅读宽度", async () => {
  const cssUrl = new URL("../../../app/globals.css", import.meta.url);
  const source = await readFile(cssUrl, "utf8");

  assert.match(source, /min-width:\s*1440px/);
  assert.match(
    source,
    /grid-template-columns:\s*minmax\(220px,\s*280px\)\s+minmax\(640px,\s*1fr\)\s+minmax\(380px,\s*440px\)/,
  );
  assert.match(source, /@media \(min-width: 1920px\)/);
  assert.match(source, /chapter-reading-content[\s\S]{0,140}max-width:/);
  assert.match(source, /@media \(max-width: 1439px\)/);
});

test("桌面工作区为右上角用户浮层预留空间", async () => {
  const cssUrl = new URL("../../../app/globals.css", import.meta.url);
  const source = await readFile(cssUrl, "utf8");

  assert.match(source, /\.workspace-shell-header[\s\S]{0,220}padding-right:\s*240px/);
  assert.match(source, /\.home-header[\s\S]{0,160}padding-right:\s*240px/);
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
