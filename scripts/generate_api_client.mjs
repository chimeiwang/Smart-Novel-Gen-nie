import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import openapiTS, { astToString } from "openapi-typescript";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const target = path.join(root, "packages", "api-client", "src", "generated", "schema.d.ts");
const temporary = mkdtempSync(path.join(tmpdir(), "inkforge-openapi-"));
const openapiPath = path.join(temporary, "openapi.json");
const uvCommand = process.platform === "win32" ? "py" : "uv";
const uvArgs =
  process.platform === "win32"
    ? ["-m", "uv", "run", "python", "scripts/export_openapi.py", "--output", openapiPath]
    : ["run", "python", "scripts/export_openapi.py", "--output", openapiPath];

function normalizeLineEndings(value) {
  return value.replace(/\r\n?/g, "\n");
}

try {
  execFileSync(uvCommand, uvArgs, {
    cwd: root,
    stdio: "inherit",
  });
  const ast = await openapiTS(pathToFileURL(openapiPath));
  const generated = astToString(ast);
  if (process.argv.includes("--check")) {
    let current = "";
    try {
      current = readFileSync(target, "utf8");
    } catch {
      throw new Error("生成的 API 客户端不存在，请先运行 npm run api:generate");
    }
    if (normalizeLineEndings(current) !== normalizeLineEndings(generated)) {
      throw new Error("生成的 API 客户端与 Core OpenAPI 不一致");
    }
  } else {
    mkdirSync(path.dirname(target), { recursive: true });
    writeFileSync(target, generated, "utf8");
  }
} finally {
  rmSync(temporary, { recursive: true, force: true });
}
