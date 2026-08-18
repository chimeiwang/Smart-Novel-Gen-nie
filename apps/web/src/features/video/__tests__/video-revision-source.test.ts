import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("待审视频候选提供必填返工意见和稳定幂等键", async () => {
  const stageUrl = new URL("../video-foundation-stage.tsx", import.meta.url);
  const source = await readFile(stageUrl, "utf8");

  assert.match(source, /返工意见（必填）/);
  assert.match(source, /name="userMessage"[\s\S]{0,80}required/);
  assert.match(source, /useState\(\(\) => createClientRequestId\(\)\)/);
  assert.match(source, /MAX_REVISION_MESSAGE_CHARACTERS = 2_000/);
  assert.match(source, /artifactRevision[\s\S]{0,160}clientRequestId/);
  assert.match(source, /working === `approve:\$\{sceneId\}` \|\| working === `revise:\$\{sceneId\}`/);
  assert.match(source, /返工并重新生成/);
});

test("视频工作台把返工提交到同一场景并清除旧预览", async () => {
  const workspaceUrl = new URL("../video-workspace.tsx", import.meta.url);
  const source = await readFile(workspaceUrl, "utf8");

  assert.match(source, /"\/api\/v1\/video\/scenes\/\{scene_id\}\/revise"/);
  assert.match(source, /path: \{ scene_id: sceneId \}/);
  assert.match(source, /body: \{[\s\S]{0,180}clientRequestId,[\s\S]{0,80}expectedArtifactRevision,[\s\S]{0,80}userMessage,/);
  assert.match(source, /setPreviewSelections\(\{\}\);[\s\S]{0,80}setPromptPreview\(null\)/);
  assert.match(source, /loadProject\(activeProjectId, result\.scene\.id\)/);
  assert.match(source, /setStage\("foundation"\)/);
});

test("视频来源只能从当前章节选区提交并绑定章节版本", async () => {
  const [stageSource, workspaceSource] = await Promise.all([
    readFile(new URL("../video-source-stage.tsx", import.meta.url), "utf8"),
    readFile(new URL("../video-workspace.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(stageSource, /value=\{chapterContent\}[\s\S]{0,100}readOnly/);
  assert.match(stageSource, /selectionStart/);
  assert.match(stageSource, /selectionEnd/);
  assert.match(stageSource, /chapterContent\.slice\(start, end\)/);
  assert.doesNotMatch(stageSource, /onChange=\{\(event\) => props\.onSourceTextChange/);
  assert.match(workspaceSource, /clientRequestId,/);
  assert.match(workspaceSource, /expectedChapterUpdatedAt: currentChapter\.updatedAt/);
  assert.match(workspaceSource, /selectionStartUtf16: selectedStartUtf16/);
  assert.match(workspaceSource, /selectionEndUtf16: selectedEndUtf16/);
  assert.match(workspaceSource, /selectedText: selectedSourceText/);
});

test("视频批准绑定候选 revision 并复用稳定请求标识", async () => {
  const [stageSource, workspaceSource] = await Promise.all([
    readFile(new URL("../video-foundation-stage.tsx", import.meta.url), "utf8"),
    readFile(new URL("../video-workspace.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(stageSource, /CandidateApprovalButton/);
  assert.match(stageSource, /useState\(\(\) => createClientRequestId\(\)\)/);
  assert.match(stageSource, /onApproveScene\(sceneId, artifactRevision, clientRequestId\)/);
  assert.match(workspaceSource, /"\/api\/v1\/video\/scenes\/\{scene_id\}\/approve"/);
  assert.match(workspaceSource, /body: \{ clientRequestId, expectedArtifactRevision \}/);
});
