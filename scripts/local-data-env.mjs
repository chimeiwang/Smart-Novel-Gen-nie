import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { parseEnv } from "node:util";

export const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function decodeUrlPart(value, name) {
  try {
    return decodeURIComponent(value);
  } catch {
    throw new Error(`${name} 的凭据编码无效。`);
  }
}

function parseUrl(value, name) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} 缺失。`);
  }

  try {
    return new URL(value);
  } catch {
    throw new Error(`${name} 格式无效。`);
  }
}

export function validateLocalDataEnv(env) {
  const postgresUrl = parseUrl(env.DATABASE_URL, "DATABASE_URL");
  const redisUrl = parseUrl(env.REDIS_URL, "REDIS_URL");

  const postgresValid =
    postgresUrl.protocol === "postgresql+asyncpg:" &&
    postgresUrl.hostname === "127.0.0.1" &&
    postgresUrl.port === "5432" &&
    postgresUrl.pathname === "/inkforge_local" &&
    postgresUrl.username.length > 0 &&
    postgresUrl.password.length > 0 &&
    postgresUrl.search === "" &&
    postgresUrl.hash === "";
  if (!postgresValid) {
    throw new Error(
      "DATABASE_URL 必须指向带密码的本地 PostgreSQL 127.0.0.1:5432/inkforge_local。",
    );
  }

  const redisValid =
    redisUrl.protocol === "redis:" &&
    redisUrl.hostname === "127.0.0.1" &&
    redisUrl.port === "6379" &&
    redisUrl.pathname === "/0" &&
    redisUrl.password.length > 0 &&
    redisUrl.search === "" &&
    redisUrl.hash === "";
  if (!redisValid) {
    throw new Error("REDIS_URL 必须指向带密码的本地 Redis 127.0.0.1:6379/0。");
  }

  return {
    postgres: {
      database: "inkforge_local",
      host: "127.0.0.1",
      password: decodeUrlPart(postgresUrl.password, "DATABASE_URL"),
      port: 5432,
      username: decodeUrlPart(postgresUrl.username, "DATABASE_URL"),
    },
    redis: {
      database: 0,
      host: "127.0.0.1",
      password: decodeUrlPart(redisUrl.password, "REDIS_URL"),
      port: 6379,
    },
  };
}

export function loadLocalDataEnv({
  root = repositoryRoot,
  parentEnv = process.env,
  readFile = readFileSync,
} = {}) {
  const envFile = path.join(root, ".env.local");
  let fileEnv;
  try {
    fileEnv = parseEnv(readFile(envFile, "utf8"));
  } catch (error) {
    if (error?.code === "ENOENT") {
      throw new Error("缺少 .env.local，请先运行 npm run data:setup。");
    }
    throw error;
  }

  const missing = ["DATABASE_URL", "REDIS_URL"].filter((key) => !fileEnv[key]?.trim());
  if (missing.length > 0) {
    throw new Error(`.env.local 缺少 ${missing.join("、")}。`);
  }

  const childEnv = {
    ...fileEnv,
    ...parentEnv,
    DATABASE_URL: fileEnv.DATABASE_URL,
    REDIS_URL: fileEnv.REDIS_URL,
  };
  validateLocalDataEnv(childEnv);
  return childEnv;
}

export function resolveLocalDataPaths({
  condaEnv,
  localAppData = process.env.LOCALAPPDATA,
  userProfile = process.env.USERPROFILE,
  fileExists = existsSync,
} = {}) {
  if (!localAppData) {
    throw new Error("无法定位 LOCALAPPDATA。请在 Windows 用户环境中运行本地数据脚本。");
  }
  if (!condaEnv && !userProfile) {
    throw new Error("无法定位 USERPROFILE。请显式提供 Conda 环境路径。");
  }

  const resolvedCondaEnv = condaEnv ?? path.join(userProfile, ".conda", "envs", "inkforge-data");
  const postgresBinCandidates = [
    path.join(resolvedCondaEnv, "Library", "bin"),
    path.join(resolvedCondaEnv, "bin"),
  ];
  const postgresBin =
    postgresBinCandidates.find((candidate) => fileExists(path.join(candidate, "pg_ctl.exe"))) ??
    postgresBinCandidates[0];
  const inkForgeRoot = path.join(localAppData, "InkForge");
  const postgresRoot = path.join(inkForgeRoot, "postgres");
  const memuraiRoot = path.join(inkForgeRoot, "memurai");
  const memuraiInstall = path.join("C:\\", "Program Files", "Memurai");

  return {
    condaEnv: resolvedCondaEnv,
    postgresBin,
    postgresData: path.join(postgresRoot, "data"),
    postgresLog: path.join(postgresRoot, "postgres.log"),
    postgresPasswordFile: path.join(postgresRoot, "initdb-password.txt"),
    initdb: path.join(postgresBin, "initdb.exe"),
    pgCtl: path.join(postgresBin, "pg_ctl.exe"),
    pgIsReady: path.join(postgresBin, "pg_isready.exe"),
    psql: path.join(postgresBin, "psql.exe"),
    createdb: path.join(postgresBin, "createdb.exe"),
    memuraiRoot,
    memuraiConfig: path.join(memuraiRoot, "memurai.conf"),
    memuraiLog: path.join(memuraiRoot, "memurai.log"),
    memuraiExe: path.join(memuraiInstall, "memurai.exe"),
    memuraiCli: path.join(memuraiInstall, "memurai-cli.exe"),
    envBackupRoot: path.join(inkForgeRoot, "backups"),
  };
}
