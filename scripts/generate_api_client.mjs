import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import openapiTS, { astToString } from "openapi-typescript";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const target = path.join(root, "packages", "api-client", "src", "generated", "schema.d.ts");
const temporary = mkdtempSync(path.join(tmpdir(), "inkforge-openapi-"));
const openapiPath = path.join(temporary, "openapi.json");
const localPython = path.join(root, ".venv", "bin", "python");
// Codex 桌面环境可能没有 uv 命令，但项目已存在受控 .venv；生成结果仍走同一导出脚本。
const useLocalPython = process.platform !== "win32" && existsSync(localPython);
const uvCommand = useLocalPython ? localPython : process.platform === "win32" ? "py" : "uv";
const uvArgs = useLocalPython
  ? ["scripts/export_openapi.py", "--output", openapiPath]
  : process.platform === "win32"
    ? ["-m", "uv", "run", "python", "scripts/export_openapi.py", "--output", openapiPath]
    : ["run", "python", "scripts/export_openapi.py", "--output", openapiPath];

function normalizeLineEndings(value) {
  return value.replace(/\r\n?/g, "\n");
}

function omitNumericDiscriminators(value) {
  if (Array.isArray(value)) {
    value.forEach(omitNumericDiscriminators);
    return;
  }
  if (value === null || typeof value !== "object") {
    return;
  }

  const mapping = value.discriminator?.mapping;
  if (
    mapping !== null &&
    typeof mapping === "object" &&
    !Array.isArray(mapping) &&
    Object.keys(mapping).length > 0 &&
    Object.keys(mapping).every((key) => /^\d+$/.test(key))
  ) {
    // OpenAPI 的 discriminator mapping key 按规范只能是字符串；openapi-typescript
    // 会据此把真实的整数 const 1/2 错投影为字符串字面量。TS 联合仍由分支中的
    // 数字 const 完整判别，因此只在生成器输入副本中移除这层元数据。
    delete value.discriminator;
  }
  Object.values(value).forEach(omitNumericDiscriminators);
}

try {
  execFileSync(uvCommand, uvArgs, {
    cwd: root,
    stdio: "inherit",
  });
  const openapi = JSON.parse(readFileSync(openapiPath, "utf8"));
  omitNumericDiscriminators(openapi);
  const ast = await openapiTS(openapi);
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
