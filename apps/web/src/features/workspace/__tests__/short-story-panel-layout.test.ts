import assert from "node:assert/strict";
import test from "node:test";

type LayoutModule = typeof import("../short-story/short-story-panel-layout");

async function loadLayoutModule(): Promise<LayoutModule> {
  try {
    return await import("../short-story/short-story-panel-layout");
  } catch {
    assert.fail("中短篇分栏布局模块尚未实现");
  }
}

test("中短篇分栏布局使用稳定的像素约束", async () => {
  const layout = await loadLayoutModule();

  assert.deepEqual(layout.SHORT_STORY_PANEL_CONSTRAINTS, {
    workflow: { defaultSize: 280, minSize: 220, maxSize: 360 },
    canvas: { minSize: 640 },
    chat: { defaultSize: 400, minSize: 320, maxSize: 520 },
  });
});

test("中短篇分栏布局按小说隔离浏览器存储键", async () => {
  const layout = await loadLayoutModule();

  assert.equal(
    layout.buildShortStoryPanelStorageKey("novel-123"),
    "inkforge:short-story-panel-layout:v1:novel-123",
  );
});

test("中短篇分栏布局只读取完整的有限正数布局", async () => {
  const layout = await loadLayoutModule();
  const valid = {
    "short-story-workflow": 280,
    "short-story-canvas": 900,
    "short-story-chat": 400,
  };
  const values = new Map<string, string>([
    [layout.buildShortStoryPanelStorageKey("valid"), JSON.stringify(valid)],
    [layout.buildShortStoryPanelStorageKey("missing"), JSON.stringify({ "short-story-workflow": 280 })],
    [layout.buildShortStoryPanelStorageKey("negative"), JSON.stringify({ ...valid, "short-story-chat": -1 })],
    [layout.buildShortStoryPanelStorageKey("broken"), "{not-json"],
  ]);
  const storage = {
    getItem(key: string) {
      return values.get(key) ?? null;
    },
    setItem() {},
  };

  assert.deepEqual(layout.readShortStoryPanelLayout(storage, "valid"), valid);
  assert.equal(layout.readShortStoryPanelLayout(storage, "missing"), null);
  assert.equal(layout.readShortStoryPanelLayout(storage, "negative"), null);
  assert.equal(layout.readShortStoryPanelLayout(storage, "broken"), null);
});

test("中短篇分栏布局在浏览器存储异常时静默回退", async () => {
  const layout = await loadLayoutModule();
  const failingStorage = {
    getItem(): string | null {
      throw new Error("读取被拒绝");
    },
    setItem(): void {
      throw new Error("写入被拒绝");
    },
  };
  const value = {
    "short-story-workflow": 280,
    "short-story-canvas": 900,
    "short-story-chat": 400,
  };

  assert.equal(layout.readShortStoryPanelLayout(failingStorage, "novel-123"), null);
  assert.doesNotThrow(() => layout.writeShortStoryPanelLayout(failingStorage, "novel-123", value));
});
