import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import net from "node:net";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import {
  loadLocalDataEnv,
  resolveLocalDataPaths,
  validateLocalDataEnv,
} from "./local-data-env.mjs";

function defaultRunCommand(command, args, options) {
  return spawnSync(command, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
    ...options,
  });
}

function defaultDelay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export function isPortOpen(host, port, { timeoutMs = 500 } = {}) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host, port });
    let settled = false;
    const finish = (open) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(open);
    };

    socket.setTimeout(timeoutMs);
    socket.once("connect", () => finish(true));
    socket.once("timeout", () => finish(false));
    socket.once("error", () => finish(false));
  });
}

function requireFile(file, name, fileExists) {
  if (!fileExists(file)) {
    throw new Error(`${name} 不存在：${file}`);
  }
}

function postgresInstallHint(paths) {
  return `请确认用户 Conda 环境 ${paths.condaEnv} 已安装 PostgreSQL 16.9 与 pgvector 0.8。`;
}

function checkPostgres(target, env, paths, runCommand) {
  const result = runCommand(
    paths.psql,
    [
      "--no-psqlrc",
      "--no-password",
      "--quiet",
      "--tuples-only",
      "--no-align",
      "--host",
      target.host,
      "--port",
      String(target.port),
      "--dbname",
      target.database,
      "--username",
      target.username,
      "--command",
      "SELECT current_database() || chr(31) || current_user;",
    ],
    { env: { ...env, PGPASSWORD: target.password } },
  );
  return (
    !result.error &&
    result.status === 0 &&
    result.stdout.trim() === `${target.database}\u001f${target.username}`
  );
}

function checkMemurai(target, env, paths, runCommand) {
  const result = runCommand(
    paths.memuraiCli,
    ["-h", target.host, "-p", String(target.port), "-n", String(target.database), "PING"],
    { env: { ...env, REDISCLI_AUTH: target.password } },
  );
  return !result.error && result.status === 0 && result.stdout.trim() === "PONG";
}

async function waitForMemurai({
  check,
  delay,
  intervalMs,
  timeoutMs,
  now,
  getStartError,
}) {
  const deadline = now() + timeoutMs;
  while (true) {
    if (getStartError()) {
      throw new Error("Memurai 进程启动失败。请检查安装路径和本地配置。");
    }
    if (check()) return;
    if (now() >= deadline) {
      throw new Error("Memurai 启动后未能在限定时间内通过 PING。");
    }
    await delay(intervalMs);
  }
}

export async function ensureLocalData(
  env,
  {
    paths = resolveLocalDataPaths({
      localAppData: env.LOCALAPPDATA,
      userProfile: env.USERPROFILE,
    }),
    fileExists = existsSync,
    isPortOpen: checkPort = isPortOpen,
    runCommand = defaultRunCommand,
    spawnDetached = spawn,
    delay = defaultDelay,
    now = Date.now,
    intervalMs = 200,
    timeoutMs = 15_000,
  } = {},
) {
  const targets = validateLocalDataEnv(env);
  requireFile(paths.psql, "psql.exe", fileExists);
  requireFile(paths.memuraiCli, "memurai-cli.exe", fileExists);

  const [postgresOpen, redisOpen] = await Promise.all([
    checkPort(targets.postgres.host, targets.postgres.port),
    checkPort(targets.redis.host, targets.redis.port),
  ]);

  if (postgresOpen) {
    if (!checkPostgres(targets.postgres, env, paths, runCommand)) {
      throw new Error(
        "端口 5432 已被占用，但 PostgreSQL 健康检查失败；不会停止或接管现有进程。",
      );
    }
  } else {
    requireFile(paths.pgCtl, "pg_ctl.exe", fileExists);
    requireFile(paths.postgresData, "PostgreSQL 数据目录", fileExists);
    const started = runCommand(
      paths.pgCtl,
      ["start", "-D", paths.postgresData, "-l", paths.postgresLog, "-w"],
      { env },
    );
    if (started.error || started.status !== 0) {
      throw new Error(`PostgreSQL 启动失败。${postgresInstallHint(paths)}日志：${paths.postgresLog}`);
    }
    if (!checkPostgres(targets.postgres, env, paths, runCommand)) {
      throw new Error(`PostgreSQL 启动后健康检查失败。请检查日志：${paths.postgresLog}`);
    }
  }

  if (redisOpen) {
    if (!checkMemurai(targets.redis, env, paths, runCommand)) {
      throw new Error("端口 6379 已被占用，但 Memurai PING 失败；不会停止或接管现有进程。");
    }
  } else {
    requireFile(paths.memuraiExe, "memurai.exe", fileExists);
    requireFile(paths.memuraiConfig, "Memurai 配置", fileExists);
    let startError = null;
    const child = spawnDetached(paths.memuraiExe, [paths.memuraiConfig], {
      cwd: paths.memuraiRoot,
      detached: true,
      env,
      stdio: "ignore",
      windowsHide: true,
    });
    child.on?.("error", (error) => {
      startError = error;
    });
    child.unref();
    await waitForMemurai({
      check: () => checkMemurai(targets.redis, env, paths, runCommand),
      delay,
      getStartError: () => startError,
      intervalMs,
      now,
      timeoutMs,
    });
  }
}

export async function main() {
  const env = loadLocalDataEnv();
  await ensureLocalData(env);
  console.log("本地 PostgreSQL 与 Memurai 已就绪。");
}

const entry = process.argv[1] ? path.resolve(process.argv[1]) : "";
if (entry === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
