import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("工作区外壳常驻挂载三类主要面板", async () => {
  const longWorkspaceUrl = new URL("../long-serial-workspace.tsx", import.meta.url);
  const source = await readFile(longWorkspaceUrl, "utf8");

  assert.match(source, /"AI 创作"/);
  assert.match(source, /"阅读与小修"/);
  assert.match(source, /"创作资料"/);
  assert.match(source, /history\.replaceState/);
  assert.match(source, /<SmartWritingPanel/);
  assert.match(source, /<ChapterEditor/);
  assert.match(source, /<LibraryPane/);
  assert.doesNotMatch(source, /SidebarTabs|showChapters/);
  assert.match(source, /hidden=\{activeView !== "library"\}/);
  assert.match(source, /workspace-editor-pane" hidden=\{activeView !== "reading"\}/);
  assert.doesNotMatch(source, /key=\{activeView\}/);
  assert.match(source, /<aside[^>]+id="workspace-review-rail"/);
  assert.doesNotMatch(source, /workspace-review-rail[^>]+hidden=/);
  assert.match(source, /countUnhandledQualityChecks\([\s\S]{0,100}currentChapter\.qualityChecks\.filter/);
  assert.doesNotMatch(source, /check\.status === "pending" \|\| check\.status === "failed"/);
});

test("审核内容与审核弹窗使用独立 portal host", async () => {
  const conversationUrl = new URL("../../writing/writing-conversation.tsx", import.meta.url);
  const source = await readFile(conversationUrl, "utf8");

  assert.match(source, /createPortal/);
  assert.match(source, /getElementById\("workspace-review-rail"\)/);
  assert.match(source, /createPortal\([\s\S]*document\.body/);
  assert.match(source, /当前没有待确认变更/);
  assert.match(source, /useSyncExternalStore/);
  assert.match(source, /document\.getElementById\("workspace-review-rail"\)/);
  assert.match(source, /function getServerReviewRailHostSnapshot[\s\S]{0,120}return null/);
  assert.doesNotMatch(source, /setReviewRailHost/);
  assert.doesNotMatch(source, /const reviewRailHost = typeof document/);
});

test("审核弹窗 portal 根节点命中全屏遮罩样式", async () => {
  const conversationUrl = new URL("../../writing/writing-conversation.tsx", import.meta.url);
  const cssUrl = new URL("../../writing/writing-conversation.css", import.meta.url);
  const [conversationSource, cssSource] = await Promise.all([
    readFile(conversationUrl, "utf8"),
    readFile(cssUrl, "utf8"),
  ]);

  assert.match(conversationSource, /className="writing-chat modal-overlay"/);
  assert.match(
    cssSource,
    /\.writing-chat\.modal-overlay,\s*\.writing-chat \.modal-overlay\s*\{[\s\S]{0,220}z-index:\s*1000/,
  );
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
  const longWorkspaceUrl = new URL("../long-serial-workspace.tsx", import.meta.url);
  const source = await readFile(longWorkspaceUrl, "utf8");

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
    /grid-template-columns:\s*minmax\(240px,\s*280px\)\s+minmax\(0,\s*1fr\)\s+minmax\(340px,\s*400px\)/,
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

test("创作台更多按钮不竖排且空审核栏不显示零计数", async () => {
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
    /reviewRailArtifacts\.length > 0 \? \([\s\S]{0,140}<small>本章待确认/,
  );
});
