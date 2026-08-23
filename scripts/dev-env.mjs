import { readFileSync } from "node:fs";
import process from "node:process";

const DATA_KEYS = ["DATABASE_URL", "REDIS_URL"];

export function mergeDevelopmentEnv(fileEnv, parentEnv) {
  const missing = DATA_KEYS.filter((key) => !fileEnv[key]?.trim());
  if (missing.length > 0) {
    throw new Error(`.env.local 缺少配置：${missing.join("、")}`);
  }

  return {
    ...fileEnv,
    ...parentEnv,
    DATABASE_URL: fileEnv.DATABASE_URL,
    REDIS_URL: fileEnv.REDIS_URL,
  };
}

export async function loadDevelopmentEnv(
  envFile,
  { parentEnv = process.env, readFile = readFileSync } = {},
) {
  // parseEnv 从 Node 20.12 起可用；dev.mjs 会先给出明确版本错误再动态调用这里。
  const { parseEnv } = await import("node:util");
  return mergeDevelopmentEnv(parseEnv(readFile(envFile, "utf8")), parentEnv);
}
