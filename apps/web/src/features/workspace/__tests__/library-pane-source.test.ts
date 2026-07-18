import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

test("创作资料使用独立三组分类导航", async () => {
  const paneUrl = new URL("../library-pane.tsx", import.meta.url);
  const source = await readFile(paneUrl, "utf8");

  for (const label of [
    "设定", "角色", "地点", "势力", "物品", "术语", "故事背景", "世界设定",
    "故事规划", "大纲", "剧情进度", "故事进展",
    "写作规则与素材", "作品圣经", "文风", "参考资料",
  ]) {
    assert.match(source, new RegExp(`label: "${label}"`), label);
  }
  assert.match(source, /DeferredWorkspaceLoader/);
  assert.match(source, /groupForTab\(activeItem\)/);
  assert.match(source, /loader\.load\(group\)/);
  assert.match(source, /subscribeWorkspaceInvalidation/);
  assert.match(source, /loader\.invalidate\(group\)/);
  assert.match(source, /loader\.retry\(group\)/);
  assert.doesNotMatch(source, /Promise\.all\(\[\s*loader\.load\("lore"\)/);
});

test("资料详情使用主画布分区而不是完整表单弹窗", async () => {
  const paneUrl = new URL("../library-pane.tsx", import.meta.url);
  const source = await readFile(paneUrl, "utf8");

  assert.match(source, /library-pane-navigation/);
  assert.match(source, /library-pane-detail/);
  assert.doesNotMatch(source, /<Modal/);
});

test("三个规划长文本编辑器切换时使用独立实例", async () => {
  const paneUrl = new URL("../library-pane.tsx", import.meta.url);
  const source = await readFile(paneUrl, "utf8");

  for (const item of ["storyProgress", "storyBackground", "worldSetting"]) {
    assert.match(
      source,
      new RegExp(`<PlanningTextEditor key="${item}"`),
      item,
    );
  }
});

test("旧检查器与临时侧栏已删除", async () => {
  await assert.rejects(access(new URL("../inspector-tabs.tsx", import.meta.url)));
  await assert.rejects(access(new URL("../sidebar-tabs.tsx", import.meta.url)));
});

test("LorePanel 编辑层不再写死旧三栏位置", async () => {
  const loreUrl = new URL("../../lore/lore-panel.tsx", import.meta.url);
  const source = await readFile(loreUrl, "utf8");
  const overlay = source.match(/\.lore-fullscreen-overlay[\s\S]*?\}/)?.[0] ?? "";

  assert.match(overlay, /position:\s*absolute/);
  assert.match(overlay, /inset:\s*0/);
  assert.doesNotMatch(overlay, /left:\s*320px|right:\s*560px|margin-top|100vh/);
});

test("作品圣经只读展示篇幅类型且保存时不提交篇幅类型", async () => {
  const paneUrl = new URL("../library-pane.tsx", import.meta.url);
  const source = await readFile(paneUrl, "utf8");
  const editor = source.match(/function WritingBibleEditor[\s\S]*?export function LibraryPane/)?.[0] ?? "";
  const saveBody = editor.match(/body:\s*\{[\s\S]*?\n\s*\},/)?.[0] ?? "";

  assert.match(editor, /篇幅类型/);
  assert.match(editor, /STORY_LENGTH_PROFILE_CONFIG\[form\.storyLengthProfile\]\.label/);
  assert.doesNotMatch(editor, /selectProfile|onClick=\{\(\) => selectProfile/);
  assert.doesNotMatch(saveBody, /\.\.\.form|storyLengthProfile/);
});
