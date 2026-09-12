import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import openapiTS, { astToString } from "openapi-typescript";
import { buildCoreContract } from "./build_core_openapi.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const publicOpenApiPath = path.join(root, "contracts", "core", "public-openapi.json");
const target = path.join(root, "packages", "api-client", "src", "generated", "schema.d.ts");

function normalizeLineEndings(value) {
  return value.replace(/\r\n?/g, "\n");
}

/**
 * 将 Java 3.0.3 归一化扩展还原为 TypeScript 需要的 const/null 语义。
 * 仅修改内存副本，canonical 和 public 投影始终保留 Java 生成所需扩展。
 */
export function normalizeForTypeScript(value) {
  if (Array.isArray(value)) return value.map(normalizeForTypeScript);
  if (value === null || typeof value !== "object") return value;

  const nullable = value.nullable === true || value["x-inkforge-source-nullable"] === true;
  const fixedNull = value["x-inkforge-fixed-null"] === true;
  const constant = value["x-inkforge-const"];
  const normalized = Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => key !== "nullable" && !key.startsWith("x-inkforge-"))
      .map(([key, child]) => [key, normalizeForTypeScript(child)]),
  );

  if (constant !== undefined) normalized.const = constant;
  if (fixedNull) {
    // Java 的生成器无法表达 OpenAPI 3.1 enum:[null]，但 TS 需要保留“固定为 null”。
    normalized.enum = [null];
    return normalized;
  }
  if (nullable) return { anyOf: [normalized, { type: "null" }] };
  return normalized;
}

async function generate() {
  if (!existsSync(publicOpenApiPath)) {
    throw new Error("缺少 contracts/core/public-openapi.json，请先运行 npm run core:contract");
  }
  const openapi = normalizeForTypeScript(JSON.parse(readFileSync(publicOpenApiPath, "utf8")));
  // discriminator mapping key 按 OpenAPI 3.0 必须是字符串，但旧生成器会把纯数字映射
  // 误判为 TS 字符串判别器；分支中的数字 const 才是实际判别依据。
  function omitNumericDiscriminators(value) {
    if (Array.isArray(value)) return value.forEach(omitNumericDiscriminators);
    if (value === null || typeof value !== "object") return;
    const mapping = value.discriminator?.mapping;
    if (mapping && typeof mapping === "object" && !Array.isArray(mapping) &&
        Object.keys(mapping).length > 0 && Object.keys(mapping).every((key) => /^\d+$/.test(key))) {
      delete value.discriminator;
    }
    Object.values(value).forEach(omitNumericDiscriminators);
  }
  omitNumericDiscriminators(openapi);
  return astToString(await openapiTS(openapi));
}

async function main() {
  const check = process.argv.includes("--check");
  // 同一入口核对 canonical 到公共投影再到 TS，不能只比较两份过期生成物。
  buildCoreContract({ check });
  const generated = await generate();
  if (check) {
    let current = "";
    try { current = readFileSync(target, "utf8"); } catch {
      throw new Error("生成的 API 客户端不存在，请先运行 npm run api:generate");
    }
    if (normalizeLineEndings(current) !== normalizeLineEndings(generated)) {
      throw new Error("生成的 API 客户端与 Core OpenAPI 不一致");
    }
  } else {
    mkdirSync(path.dirname(target), { recursive: true });
    writeFileSync(target, generated, "utf8");
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main();
