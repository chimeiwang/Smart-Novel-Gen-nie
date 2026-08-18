import { readFileSync } from "node:fs";
import process from "node:process";
import { parseEnv } from "node:util";

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

export function loadDevelopmentEnv(
  envFile,
  { parentEnv = process.env, readFile = readFileSync } = {},
) {
  return mergeDevelopmentEnv(parseEnv(readFile(envFile, "utf8")), parentEnv);
}
