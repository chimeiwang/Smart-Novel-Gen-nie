import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("共享工作区弹窗提供遮罩、标题栏、关闭按钮和滚动内容区", async () => {
  const dialogUrl = new URL("../workspace-dialog.tsx", import.meta.url);
  const cssUrl = new URL("../../../app/globals.css", import.meta.url);
  const [dialogSource, cssSource] = await Promise.all([
    readFile(dialogUrl, "utf8"),
    readFile(cssUrl, "utf8"),
  ]);

  assert.match(dialogSource, /workspace-dialog-overlay/);
  assert.match(dialogSource, /workspace-dialog-panel/);
  assert.match(dialogSource, /workspace-dialog-header/);
  assert.match(dialogSource, /workspace-dialog-body/);
  assert.match(dialogSource, /aria-modal="true"/);
  assert.match(cssSource, /\.workspace-dialog-overlay[\s\S]{0,260}position:\s*fixed/);
  assert.match(cssSource, /\.workspace-dialog-body[\s\S]{0,180}overflow:\s*auto/);
  assert.match(cssSource, /\.workspace-dialog-panel\.library/);
  assert.match(cssSource, /\.workspace-dialog-panel\.review/);
});
