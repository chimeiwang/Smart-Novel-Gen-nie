import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import {
  loadLocalDataEnv,
  resolveLocalDataPaths,
  validateLocalDataEnv,
} from "../../scripts/local-data-env.mjs";

const POSTGRES_URL =
  "postgresql+asyncpg://inkforge_local:local-postgres-password@127.0.0.1:5432/inkforge_local";
const REDIS_URL = "redis://:local-redis-password@127.0.0.1:6379/0";

function withTempDirectory(run) {
  const directory = mkdtempSync(path.join(tmpdir(), "inkforge-local-data-env-"));
  try {
    return run(directory);
  } finally {
    rmSync(directory, { force: true, recursive: true });
  }
}

test(".env.local 的本地数据地址覆盖父进程中的远程地址", () =>
  withTempDirectory((root) => {
    writeFileSync(
      path.join(root, ".env.local"),
      `DATABASE_URL=${POSTGRES_URL}\nREDIS_URL=${REDIS_URL}\nJWT_SECRET=local-jwt\n`,
      "utf8",
    );

    const childEnv = loadLocalDataEnv({
      root,
      parentEnv: {
        DATABASE_URL: "postgresql+asyncpg://remote:secret@203.0.113.10:5432/inkforge",
        REDIS_URL: "redis://:secret@203.0.113.10:6379/0",
        JWT_SECRET: "terminal-jwt",
        KEEP_ME: "保留",
      },
    });

    assert.equal(childEnv.DATABASE_URL, POSTGRES_URL);
    assert.equal(childEnv.REDIS_URL, REDIS_URL);
    assert.equal(childEnv.JWT_SECRET, "terminal-jwt");
    assert.equal(childEnv.KEEP_ME, "保留");
  }));

test("缺少 .env.local 中的数据地址时不回退到父进程", () =>
  withTempDirectory((root) => {
    writeFileSync(path.join(root, ".env.local"), "JWT_SECRET=local-jwt\n", "utf8");

    assert.throws(
      () =>
        loadLocalDataEnv({
          root,
          parentEnv: {
            DATABASE_URL: POSTGRES_URL,
            REDIS_URL,
          },
        }),
      /\.env\.local.*DATABASE_URL.*REDIS_URL/,
    );
  }));

for (const [name, databaseUrl, redisUrl] of [
  [
    "拒绝远程 PostgreSQL",
    "postgresql+asyncpg://inkforge_local:do-not-print@192.0.2.10:5432/inkforge_local",
    REDIS_URL,
  ],
  [
    "拒绝错误 PostgreSQL 数据库",
    "postgresql+asyncpg://inkforge_local:do-not-print@127.0.0.1:5432/inkforge",
    REDIS_URL,
  ],
  [
    "拒绝无密码 PostgreSQL",
    "postgresql+asyncpg://inkforge_local@127.0.0.1:5432/inkforge_local",
    REDIS_URL,
  ],
  [
    "拒绝远程 Redis",
    POSTGRES_URL,
    "redis://:do-not-print@192.0.2.20:6379/0",
  ],
  ["拒绝无密码 Redis", POSTGRES_URL, "redis://127.0.0.1:6379/0"],
  ["拒绝错误 Redis 数据库", POSTGRES_URL, "redis://:do-not-print@127.0.0.1:6379/1"],
]) {
  test(name, () => {
    assert.throws(
      () => validateLocalDataEnv({ DATABASE_URL: databaseUrl, REDIS_URL: redisUrl }),
      (error) => {
        assert.doesNotMatch(error.message, /do-not-print|postgresql\+asyncpg:\/\/|redis:\/\//);
        return true;
      },
    );
  });
}

test("从 Conda 环境的 bin 目录动态定位 PostgreSQL 可执行文件", () =>
  withTempDirectory((root) => {
    const condaEnv = path.join(root, "inkforge-data");
    const postgresBin = path.join(condaEnv, "bin");
    mkdirSync(postgresBin, { recursive: true });
    writeFileSync(path.join(postgresBin, "pg_ctl.exe"), "", "utf8");

    const paths = resolveLocalDataPaths({
      condaEnv,
      localAppData: path.join(root, "local-app-data"),
      userProfile: root,
    });

    assert.equal(paths.condaEnv, condaEnv);
    assert.equal(paths.postgresBin, postgresBin);
    assert.equal(paths.postgresData, path.join(root, "local-app-data", "InkForge", "postgres", "data"));
  }));

test("默认 Conda 环境位于当前用户目录", () =>
  withTempDirectory((root) => {
    const paths = resolveLocalDataPaths({
      localAppData: path.join(root, "local-app-data"),
      userProfile: root,
    });

    assert.equal(paths.condaEnv, path.join(root, ".conda", "envs", "inkforge-data"));
  }));
