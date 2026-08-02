import { spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { repositoryRoot, resolveLocalDataPaths } from "./local-data-env.mjs";

const POSTGRES_USER = "inkforge_local";
const DATABASE_NAME = "inkforge_local";

function defaultRunCommand(command, args, options) {
  return spawnSync(command, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
    ...options,
  });
}

export function generateLocalPassword() {
  return randomBytes(32).toString("base64url");
}

function assertUnusedDataDirectory(paths, fileExists, readDirectory) {
  if (fileExists(path.join(paths.postgresData, "PG_VERSION"))) {
    throw new Error(`已有 PostgreSQL 数据：${paths.postgresData}。setup 拒绝覆盖。`);
  }
  if (fileExists(paths.postgresData) && readDirectory(paths.postgresData).length > 0) {
    throw new Error(`PostgreSQL 数据目录非空：${paths.postgresData}。setup 拒绝覆盖。`);
  }
}

function assertRequiredExecutables(paths, fileExists) {
  const postgresExecutables = [
    [paths.initdb, "initdb.exe"],
    [paths.pgCtl, "pg_ctl.exe"],
    [paths.psql, "psql.exe"],
    [paths.createdb, "createdb.exe"],
  ];
  for (const [file, name] of postgresExecutables) {
    if (!fileExists(file)) {
      throw new Error(
        `缺少 ${name}：${file}。请在 ${paths.condaEnv} 人工安装 PostgreSQL 16.9 与 pgvector 0.8。`,
      );
    }
  }

  for (const [file, name] of [
    [paths.memuraiExe, "memurai.exe"],
    [paths.memuraiCli, "memurai-cli.exe"],
  ]) {
    if (!fileExists(file)) {
      throw new Error(`缺少 ${name}：${file}。请先完成 Memurai 本机安装。`);
    }
  }
}

async function runCheckedCommand(name, command, args, options, runCommand) {
  let result;
  try {
    result = await runCommand(command, args, options);
  } catch {
    throw new Error(`${name} 执行失败。`);
  }
  if (result.error || result.status !== 0) {
    throw new Error(`${name} 执行失败。`);
  }
}

function quoteMemuraiPath(value) {
  return value.replaceAll("\\", "/").replaceAll('"', '\\"');
}

export function buildMemuraiConfig(password, paths) {
  return [
    "bind 127.0.0.1",
    "protected-mode yes",
    "port 6379",
    `requirepass ${password}`,
    'save ""',
    "appendonly no",
    `dir "${quoteMemuraiPath(paths.memuraiRoot)}"`,
    `logfile "${quoteMemuraiPath(paths.memuraiLog)}"`,
    "",
  ].join("\n");
}

export function updateLocalEnvText(source, databaseUrl, redisUrl) {
  const newline = source.includes("\r\n") ? "\r\n" : "\n";
  const updates = { DATABASE_URL: databaseUrl, REDIS_URL: redisUrl };
  const found = new Set();
  const lines = source.length > 0 ? source.split(/\r?\n/) : [];
  const updated = lines.map((line) => {
    const match = line.match(/^\s*(DATABASE_URL|REDIS_URL)\s*=/);
    if (!match) return line;
    const key = match[1];
    found.add(key);
    return `${key}=${updates[key]}`;
  });

  for (const key of ["DATABASE_URL", "REDIS_URL"]) {
    if (!found.has(key)) updated.push(`${key}=${updates[key]}`);
  }
  const text = updated.join(newline);
  return text.endsWith(newline) ? text : `${text}${newline}`;
}

function backupName(now) {
  return `.env.local.${new Date(now).toISOString().replaceAll(/[-:.]/g, "")}.bak`;
}

export async function setupLocalData(options = {}) {
  const root = options.root ?? repositoryRoot;
  const env = options.env ?? process.env;
  const paths =
    options.paths ??
    resolveLocalDataPaths({
      localAppData: env.LOCALAPPDATA,
      userProfile: env.USERPROFILE,
    });
  const fileExists = options.fileExists ?? existsSync;
  const readDirectory = options.readDirectory ?? readdirSync;
  const makeDirectory = options.makeDirectory ?? mkdirSync;
  const readFile = options.readFile ?? readFileSync;
  const writeFile = options.writeFile ?? writeFileSync;
  const copyFile = options.copyFile ?? copyFileSync;
  const removeFile = options.removeFile ?? rmSync;
  const runCommand = options.runCommand ?? defaultRunCommand;
  const randomPassword = options.randomPassword ?? generateLocalPassword;
  const now = options.now ?? Date.now;

  assertUnusedDataDirectory(paths, fileExists, readDirectory);
  assertRequiredExecutables(paths, fileExists);

  const postgresPassword = randomPassword();
  const memuraiPassword = randomPassword();
  makeDirectory(paths.postgresData, { recursive: true });
  makeDirectory(paths.memuraiRoot, { recursive: true });
  makeDirectory(paths.envBackupRoot, { recursive: true });

  writeFile(paths.postgresPasswordFile, `${postgresPassword}\n`, {
    encoding: "utf8",
    mode: 0o600,
  });
  try {
    await runCheckedCommand(
      "initdb",
      paths.initdb,
      [
        "-D",
        paths.postgresData,
        "--username",
        POSTGRES_USER,
        "--pwfile",
        paths.postgresPasswordFile,
        "--auth-host",
        "scram-sha-256",
        "--encoding",
        "UTF8",
      ],
      { env },
      runCommand,
    );
  } finally {
    removeFile(paths.postgresPasswordFile, { force: true });
  }

  await runCheckedCommand(
    "pg_ctl start",
    paths.pgCtl,
    ["start", "-D", paths.postgresData, "-l", paths.postgresLog, "-w"],
    { env },
    runCommand,
  );
  await runCheckedCommand(
    "createdb",
    paths.createdb,
    ["-h", "127.0.0.1", "-p", "5432", "-U", POSTGRES_USER, DATABASE_NAME],
    { env: { ...env, PGPASSWORD: postgresPassword } },
    runCommand,
  );

  writeFile(paths.memuraiConfig, buildMemuraiConfig(memuraiPassword, paths), {
    encoding: "utf8",
    mode: 0o600,
  });

  const envFile = path.join(root, ".env.local");
  let source = "";
  let backupFile = null;
  if (fileExists(envFile)) {
    source = readFile(envFile, "utf8");
    backupFile = path.join(paths.envBackupRoot, backupName(now()));
    copyFile(envFile, backupFile);
  }

  const databaseUrl = `postgresql+asyncpg://${POSTGRES_USER}:${encodeURIComponent(postgresPassword)}@127.0.0.1:5432/${DATABASE_NAME}`;
  const redisUrl = `redis://:${encodeURIComponent(memuraiPassword)}@127.0.0.1:6379/0`;
  writeFile(envFile, updateLocalEnvText(source, databaseUrl, redisUrl), {
    encoding: "utf8",
    mode: 0o600,
  });

  return { backupFile };
}

export async function main() {
  const result = await setupLocalData();
  console.log("本地 PostgreSQL 与 Memurai 首次配置已完成。");
  if (result.backupFile) console.log(`原 .env.local 已备份到：${result.backupFile}`);
}

const entry = process.argv[1] ? path.resolve(process.argv[1]) : "";
if (entry === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
