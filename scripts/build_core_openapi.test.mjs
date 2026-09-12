import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import {
  buildCoreContract,
  projectPublicOpenApi,
  stableJson,
  validateCoreOpenApi,
} from "./build_core_openapi.mjs";
import { normalizeForTypeScript } from "./generate_api_client.mjs";

function operation(exposure, operationId) {
  return {
    operationId,
    "x-inkforge-exposure": exposure,
    "x-inkforge-authentication": "public",
    "x-inkforge-product-module": "test",
    "x-inkforge-response-kind": "json",
    "x-inkforge-transaction": "read_only",
    "x-inkforge-side-effects": [],
  };
}

function fixture() {
  return {
    openapi: "3.0.3",
    info: { title: "test", version: "1" },
    paths: {
      "/api/v1/public": { get: operation("public", "get_public") },
      "/internal/v1/private": {
        post: operation("internal", "post_private"),
      },
      "/api/v1/video/provider-assets/{token}": {
        get: operation(
          "provider_media",
          "get_provider",
          "/api/v1/video/provider-assets/{token}",
        ),
      },
    },
  };
}

test("公共投影按 exposure 排除内部和 provider media", () => {
  const projected = projectPublicOpenApi(fixture());
  assert.deepEqual(Object.keys(projected.paths), ["/api/v1/public"]);
  assert.equal(projected.paths["/api/v1/public"].get.operationId, "get_public");
});

test("校验拒绝重复 operationId、缺失 exposure 与错误路径分类", () => {
  const duplicate = fixture();
  duplicate.paths["/api/v1/other"] = {
    get: operation("public", "get_public", "/api/v1/other"),
  };
  assert.throws(() => validateCoreOpenApi(duplicate), /重复 operationId/);

  const missing = fixture();
  delete missing.paths["/api/v1/public"].get["x-inkforge-exposure"];
  assert.throws(() => validateCoreOpenApi(missing), /缺少 x-inkforge-exposure/);

  const wrong = fixture();
  wrong.paths["/internal/v1/private"].post["x-inkforge-exposure"] = "public";
  assert.throws(() => validateCoreOpenApi(wrong), /public 操作必须位于 \/api\/v1\//);
});

test("stableJson 固定 LF 并以换行结尾", () => {
  assert.equal(stableJson({ b: 1, a: "中文" }), '{\n  "b": 1,\n  "a": "中文"\n}\n');
  assert.equal(stableJson({ a: "\r\n" }).includes("\r"), false);
});

test("--check 能发现公共投影漂移", () => {
  const directory = mkdtempSync(path.join(tmpdir(), "inkforge-core-contract-test-"));
  try {
    writeFileSync(path.join(directory, "openapi.json"), stableJson(fixture()));
    buildCoreContract({ contractRoot: directory });
    assert.doesNotThrow(() => buildCoreContract({ check: true, contractRoot: directory }));
    const output = path.join(directory, "public-openapi.json");
    writeFileSync(output, "{}\n", "utf8");
    assert.throws(() => buildCoreContract({ check: true, contractRoot: directory }), /存在漂移/);
    assert.equal(readFileSync(output, "utf8"), "{}\n");
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("TypeScript 投影把 OpenAPI nullable $ref 还原为可空联合", () => {
  const normalized = normalizeForTypeScript({
    $ref: "#/components/schemas/ShortMediumSourceKind",
    nullable: true,
  });
  assert.deepEqual(normalized, {
    anyOf: [
      { $ref: "#/components/schemas/ShortMediumSourceKind" },
      { type: "null" },
    ],
  });
});

test("TypeScript 投影保留数字 const 和固定 null", () => {
  assert.deepEqual(
    normalizeForTypeScript({ type: "integer", "x-inkforge-const": 2 }),
    { type: "integer", const: 2 },
  );
  assert.deepEqual(
    normalizeForTypeScript({ type: "string", nullable: true, "x-inkforge-fixed-null": true }),
    { type: "string", enum: [null] },
  );
});
