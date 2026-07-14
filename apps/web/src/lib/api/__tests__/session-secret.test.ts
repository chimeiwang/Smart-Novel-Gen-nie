import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { resolveSessionSecret } from "../../auth/session-secret";

const legacyDefault = "inkforge-default-secret-change-me";

describe("生产会话密钥", () => {
  it("拒绝生产环境缺少密钥", () => {
    assert.throws(
      () => resolveSessionSecret({ NODE_ENV: "production" }),
      /必须配置非默认 JWT_SECRET/,
    );
  });

  it("拒绝生产环境历史默认密钥", () => {
    assert.throws(
      () =>
        resolveSessionSecret({
          NODE_ENV: "production",
          JWT_SECRET: legacyDefault,
        }),
      /必须配置非默认 JWT_SECRET/,
    );
  });

  it("按 UTF-8 字节拒绝不足 32 字节的生产密钥", () => {
    assert.throws(
      () =>
        resolveSessionSecret({
          NODE_ENV: "production",
          JWT_SECRET: "不足三十二字节",
        }),
      /至少需要 32 个 UTF-8 字节/,
    );
  });

  it("接受至少 32 个 UTF-8 字节的生产密钥", () => {
    const value = resolveSessionSecret({
      NODE_ENV: "production",
      JWT_SECRET: "生产会话密钥-1234567890-abcdefghijklmnopqrstuvwxyz",
    });

    assert.ok(value.byteLength >= 32);
  });

  it("非生产环境继续使用测试默认值", () => {
    assert.deepEqual(
      resolveSessionSecret({ NODE_ENV: "test" }),
      new TextEncoder().encode(legacyDefault),
    );
  });
});
