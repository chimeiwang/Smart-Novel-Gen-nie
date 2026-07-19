import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const componentUrl = new URL(
  "../short-story/short-story-chat-pane.tsx",
  import.meta.url,
);

test("中短篇右栏只承载可新建和续接的会话", async () => {
  const source = await readFile(componentUrl, "utf8");

  assert.match(source, /历史对话/);
  assert.match(source, /开始新对话/);
  assert.match(source, /writing\/sessions/);
  assert.match(source, /versionReferences/);
  assert.doesNotMatch(source, /作品信息/);
  assert.doesNotMatch(source, /版本历史/);
  assert.doesNotMatch(source, /编辑审核/);
});

test("开始新对话只重置本地状态，首次发送才创建持久会话", async () => {
  const source = await readFile(componentUrl, "utf8");

  assert.match(
    source,
    /const startNewConversation = useCallback\(\(\) => \{[\s\S]*sessionIdRef\.current = null;[\s\S]*setSession\(null\);[\s\S]*setShowHistory\(false\);[\s\S]*setLoading\(false\);/,
  );
  assert.match(
    source,
    /onClick=\{startNewConversation\}[\s\S]*开始新对话/,
  );
  assert.match(
    source,
    /const sessionId = sessionIdRef\.current \?\? await createSession\(\);/,
  );
});

test("选择历史对话时立即清空旧消息并关闭历史列表", async () => {
  const source = await readFile(componentUrl, "utf8");

  assert.match(
    source,
    /const selectSession = useCallback\(async \(sessionId: string\) => \{[\s\S]*setSession\(null\);[\s\S]*setShowHistory\(false\);[\s\S]*setLoading\(true\);[\s\S]*await loadSession\(sessionId\);/,
  );
  assert.match(source, /if \(sessionIdRef\.current === sessionId\) setLoading\(false\);/);
});
