import { mkdtempSync, rmSync, writeFileSync } from "fs";
import os from "os";
import path from "path";
import { afterEach, describe, it } from "node:test";
import assert from "node:assert/strict";

import { readRecentNonEmptyLines } from "../workflow-event-log-reader";

const tempDirs: string[] = [];

afterEach(() => {
  for (const dir of tempDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true });
  }
});

function createTempFile(content: string): string {
  const dir = mkdtempSync(path.join(os.tmpdir(), "workflow-event-log-reader-"));
  tempDirs.push(dir);
  const file = path.join(dir, "workflow-events-2026-06-20.jsonl");
  writeFileSync(file, content, "utf-8");
  return file;
}

describe("readRecentNonEmptyLines", () => {
  it("returns only the requested recent non-empty lines", () => {
    const file = createTempFile(["old-1", "old-2", "new-1", "", "new-2", ""].join("\n"));

    const lines = readRecentNonEmptyLines(file, 2, { maxBytes: 4096, chunkSize: 8 });

    assert.deepEqual(lines, ["new-1", "new-2"]);
  });

  it("reads from the tail in chunks instead of requiring the whole file", () => {
    const file = createTempFile(Array.from({ length: 200 }, (_, index) => `line-${index}`).join("\n"));

    const lines = readRecentNonEmptyLines(file, 3, { maxBytes: 128, chunkSize: 11 });

    assert.deepEqual(lines, ["line-197", "line-198", "line-199"]);
  });
});
