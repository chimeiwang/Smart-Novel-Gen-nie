const LEGACY_DEFAULT_SECRET = "inkforge-default-secret-change-me";

export interface SessionSecretEnvironment {
  JWT_SECRET?: string;
  NODE_ENV?: string;
}

export function resolveSessionSecret(
  environment: SessionSecretEnvironment = process.env,
): Uint8Array {
  const configured = environment.JWT_SECRET;
  if (environment.NODE_ENV === "production") {
    if (!configured || configured === LEGACY_DEFAULT_SECRET) {
      throw new Error("生产环境必须配置非默认 JWT_SECRET");
    }
    if (new TextEncoder().encode(configured).byteLength < 32) {
      throw new Error("生产环境 JWT_SECRET 至少需要 32 个 UTF-8 字节");
    }
  }
  return new TextEncoder().encode(configured ?? LEGACY_DEFAULT_SECRET);
}
