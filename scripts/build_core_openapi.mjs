import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const CONTRACT_ROOT = path.join(ROOT, "contracts", "core");
const METHODS = new Set(["get", "post", "put", "patch", "delete", "options", "head", "trace"]);
const METHOD_ORDER = ["get", "post", "put", "patch", "delete", "options", "head", "trace"];
const REQUIRED_METADATA = [
  "x-inkforge-exposure",
  "x-inkforge-authentication",
  "x-inkforge-product-module",
  "x-inkforge-response-kind",
  "x-inkforge-transaction",
  "x-inkforge-side-effects",
];

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

/** 返回按路径和 HTTP 方法稳定排序的 OpenAPI 操作。 */
function operations(document) {
  return Object.entries(document.paths ?? {})
    .flatMap(([routePath, pathItem]) => METHOD_ORDER
      .filter((method) => pathItem[method])
      .map((method) => ({ path: routePath, method, operation: pathItem[method] })))
    .sort((left, right) => left.path.localeCompare(right.path) ||
      METHOD_ORDER.indexOf(left.method) - METHOD_ORDER.indexOf(right.method));
}

function collectRefs(value, refs = new Set()) {
  if (Array.isArray(value)) {
    value.forEach((item) => collectRefs(item, refs));
  } else if (value && typeof value === "object") {
    if (typeof value.$ref === "string") refs.add(value.$ref);
    Object.values(value).forEach((item) => collectRefs(item, refs));
  }
  return refs;
}

function retainReferencedSchemas(document, pathItems) {
  const allSchemas = document.components?.schemas ?? {};
  const keep = new Set();
  const pending = [...collectRefs(pathItems)]
    .filter((ref) => ref.startsWith("#/components/schemas/"))
    .map((ref) => ref.slice("#/components/schemas/".length));
  while (pending.length) {
    const name = pending.pop();
    if (!name || keep.has(name) || !allSchemas[name]) continue;
    keep.add(name);
    for (const ref of collectRefs(allSchemas[name])) {
      if (ref.startsWith("#/components/schemas/")) {
        pending.push(ref.slice("#/components/schemas/".length));
      }
    }
  }
  return Object.fromEntries(Object.entries(allSchemas).filter(([name]) => keep.has(name)));
}

/** 从完整契约生成只含 public exposure 的浏览器/CLI 投影。 */
export function projectPublicOpenApi(full) {
  validateCoreOpenApi(full);
  const projected = clone(full);
  projected.paths = {};
  for (const { path: routePath, method, operation } of operations(full)) {
    if (operation["x-inkforge-exposure"] !== "public") continue;
    projected.paths[routePath] ??= {};
    projected.paths[routePath][method] = clone(operation);
  }
  projected.components ??= {};
  projected.components.schemas = retainReferencedSchemas(full, projected.paths);
  delete projected["x-inkforge-source-contract"];
  projected["x-inkforge-source-contract"] = "openapi.json";
  return projected;
}

/** 校验契约元数据、分类和 method/path/operationId 唯一性。 */
export function validateCoreOpenApi(full) {
  if (full?.openapi !== "3.0.3") throw new Error("Core canonical OpenAPI 必须使用 3.0.3");
  const operationIds = new Set();
  const routeKeys = new Set();
  for (const { path: routePath, method, operation } of operations(full)) {
    const key = `${method.toUpperCase()} ${routePath}`;
    if (routeKeys.has(key)) throw new Error(`重复 method/path: ${key}`);
    routeKeys.add(key);
    if (typeof operation.operationId !== "string" || !operation.operationId) {
      throw new Error(`操作缺少 operationId: ${key}`);
    }
    if (operationIds.has(operation.operationId)) {
      throw new Error(`重复 operationId: ${operation.operationId}`);
    }
    operationIds.add(operation.operationId);
    for (const field of REQUIRED_METADATA) {
      if (!(field in operation)) throw new Error(`操作缺少 ${field}: ${key}`);
    }
    const exposure = operation["x-inkforge-exposure"];
    if (!["public", "internal", "provider_media"].includes(exposure)) {
      throw new Error(`非法 x-inkforge-exposure: ${key}`);
    }
    if (exposure === "public" && !routePath.startsWith("/api/v1/")) {
      throw new Error(`public 操作必须位于 /api/v1/: ${key}`);
    }
    if (exposure === "internal" && !routePath.startsWith("/internal/v1/")) {
      throw new Error(`internal 操作必须位于 /internal/v1/: ${key}`);
    }
    if (exposure === "provider_media" && routePath !== "/api/v1/video/provider-assets/{token}") {
      throw new Error(`provider_media 路径不受支持: ${key}`);
    }
    if (!Array.isArray(operation["x-inkforge-side-effects"])) {
      throw new Error(`x-inkforge-side-effects 必须为数组: ${key}`);
    }
  }
  return { operationCount: routeKeys.size, operationIds };
}

/** 输出跨平台一致的 UTF-8 LF JSON。 */
export function stableJson(value) {
  return `${JSON.stringify(value, null, 2).replace(/\r\n?/g, "\n")}\n`;
}

function routeProjection(full) {
  const routes = operations(full).map(({ path: routePath, method, operation }) => ({
    authentication: operation["x-inkforge-authentication"],
    deprecated: operation.deprecated === true,
    exposure: operation["x-inkforge-exposure"],
    method: method.toUpperCase(),
    mutation: operation["x-inkforge-mutation"] ?? ["post", "put", "patch", "delete"].includes(method),
    operationId: operation.operationId,
    path: routePath,
    productModule: operation["x-inkforge-product-module"],
    responseKind: operation["x-inkforge-response-kind"],
    sideEffects: operation["x-inkforge-side-effects"],
    statusCode: operation["x-inkforge-status-code"] ?? null,
    transaction: operation["x-inkforge-transaction"],
  }));
  return routes;
}

function artifacts(full) {
  const routes = routeProjection(full);
  const internal = routes.filter((route) => route.exposure === "internal");
  return {
    publicOpenApi: projectPublicOpenApi(full),
    routeInventory: { schemaVersion: "core-route-inventory/2.0", routes },
    internalEndpoints: { schemaVersion: "core-internal-endpoints/2.0", endpoints: internal },
  };
}

export function buildCoreContract({ check = false, contractRoot = CONTRACT_ROOT } = {}) {
  const full = JSON.parse(readFileSync(path.join(contractRoot, "openapi.json"), "utf8"));
  validateCoreOpenApi(full);
  const generated = artifacts(full);
  const outputs = new Map([
    ["public-openapi.json", generated.publicOpenApi],
    ["route-inventory.json", generated.routeInventory],
    ["internal-endpoints.json", generated.internalEndpoints],
  ]);
  const drift = [];
  for (const [name, value] of outputs) {
    const target = path.join(contractRoot, name);
    const expected = stableJson(value);
    if (check) {
      let actual = "";
      try { actual = readFileSync(target, "utf8"); } catch { actual = "<missing>"; }
      if (actual.replace(/\r\n?/g, "\n") !== expected) drift.push(name);
    } else {
      writeFileSync(target, expected, "utf8");
    }
  }
  if (drift.length) throw new Error(`Core 契约生成物存在漂移: ${drift.join(", ")}`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  buildCoreContract({ check: process.argv.includes("--check") });
}
