import assert from "node:assert/strict";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import { generateLocalPassword, setupLocalData } from "../../scripts/setup-local-data.mjs";

function withTempDirectory(run) {
  const directory = mkdtempSync(path.join(tmpdir(), "inkforge-local-data-setup-"));
  return Promise.resolve(run(directory)).finally(() => {
    rmSync(directory, { force: true, recursive: true });
  });
}

function createPaths(root) {
  const postgresBin = path.join(root, "conda", "Library", "bin");
  const postgresRoot = path.join(root, "runtime", "postgres");
  const memuraiRoot = path.join(root, "runtime", "memurai");
  const memuraiInstall = path.join(root, "Memurai");
  return {
    condaEnv: path.join(root, "conda"),
    postgresBin,
    postgresData: path.join(postgresRoot, "data"),
    postgresLog: path.join(postgresRoot, "postgres.log"),
    postgresPasswordFile: path.join(postgresRoot, "initdb-password.txt"),
    initdb: path.join(postgresBin, "initdb.exe"),
    pgCtl: path.join(postgresBin, "pg_ctl.exe"),
    pgIsReady: path.join(postgresBin, "pg_isready.exe"),
    createdb: path.join(postgresBin, "createdb.exe"),
    memuraiRoot,
    memuraiConfig: path.join(memuraiRoot, "memurai.conf"),
    memuraiLog: path.join(memuraiRoot, "memurai.log"),
    memuraiExe: path.join(memuraiInstall, "memurai.exe"),
    memuraiCli: path.join(memuraiInstall, "memurai-cli.exe"),
    envBackupRoot: path.join(root, "runtime", "backups"),
  };
}

function createRequiredExecutables(paths, omitted) {
  for (const executable of [
    paths.initdb,
    paths.pgCtl,
    paths.pgIsReady,
    paths.createdb,
    paths.memuraiExe,
    paths.memuraiCli,
  ]) {
    if (executable === omitted) continue;
    mkdirSync(path.dirname(executable), { recursive: true });
    writeFileSync(executable, "", "utf8");
  }
}

test("存在 PG_VERSION 时 setup 拒绝覆盖数据目录", async () =>
  withTempDirectory(async (root) => {
    const paths = createPaths(root);
    mkdirSync(paths.postgresData, { recursive: true });
    writeFileSync(path.join(paths.postgresData, "PG_VERSION"), "16", "utf8");
    let commandCount = 0;

    await assert.rejects(
      () =>
        setupLocalData({
          root,
          paths,
          runCommand: () => {
            commandCount += 1;
            return { status: 0 };
          },
        }),
      /已有 PostgreSQL 数据.*拒绝覆盖/,
    );
    assert.equal(commandCount, 0);
  }));

test("非空的未知 PostgreSQL 数据目录也拒绝覆盖", async () =>
  withTempDirectory(async (root) => {
    const paths = createPaths(root);
    mkdirSync(paths.postgresData, { recursive: true });
    writeFileSync(path.join(paths.postgresData, "unknown.dat"), "未知数据", "utf8");

    await assert.rejects(
      () => setupLocalData({ root, paths, runCommand: () => ({ status: 0 }) }),
      /非空.*拒绝覆盖/,
    );
  }));

test("缺少依赖时给出 PostgreSQL 16.9 与 pgvector 0.8 的人工准备提示", async () =>
  withTempDirectory(async (root) => {
    const paths = createPaths(root);
    createRequiredExecutables(paths, paths.initdb);

    await assert.rejects(
      () => setupLocalData({ root, paths, runCommand: () => ({ status: 0 }) }),
      /initdb\.exe.*PostgreSQL 16\.9.*pgvector 0\.8/,
    );
  }));

test("生成的本地密码仅包含 URL-safe 字符", () => {
  for (let index = 0; index < 20; index += 1) {
    const password = generateLocalPassword();
    assert.match(password, /^[A-Za-z0-9_-]+$/);
    assert.ok(password.length >= 32);
  }
});

test("setup 初始化本地库、备份并只更新两个数据地址且不泄露密码", async () =>
  withTempDirectory(async (root) => {
    const paths = createPaths(root);
    createRequiredExecutables(paths);
    const originalEnv = [
      "DATABASE_URL=postgresql+asyncpg://remote-user:remote-secret@192.0.2.10:5432/inkforge",
      "REDIS_URL=redis://:remote-secret@192.0.2.10:6379/0",
      "MODEL_PROVIDER=fake",
      "JWT_SECRET=保留原值",
      "",
    ].join("\n");
    writeFileSync(path.join(root, ".env.local"), originalEnv, "utf8");

    const passwords = ["postgres_URL-safe_secret", "memurai_URL-safe_secret"];
    const commands = [];
    const result = await setupLocalData({
      root,
      paths,
      env: { PATH: "测试路径" },
      now: () => new Date("2026-08-02T12:34:56.000Z"),
      randomPassword: () => passwords.shift(),
      runCommand(command, args, options) {
        commands.push({ command, args, options });
        return { status: 0, stdout: "", stderr: "" };
      },
    });

    const updatedEnv = readFileSync(path.join(root, ".env.local"), "utf8");
    assert.match(
      updatedEnv,
      /DATABASE_URL=postgresql\+asyncpg:\/\/inkforge_local:postgres_URL-safe_secret@127\.0\.0\.1:5432\/inkforge_local/,
    );
    assert.match(
      updatedEnv,
      /REDIS_URL=redis:\/\/:memurai_URL-safe_secret@127\.0\.0\.1:6379\/0/,
    );
    assert.match(updatedEnv, /MODEL_PROVIDER=fake/);
    assert.match(updatedEnv, /JWT_SECRET=保留原值/);
    assert.equal(readFileSync(result.backupFile, "utf8"), originalEnv);

    const initdb = commands.find(({ command }) => command === paths.initdb);
    const pgCtl = commands.find(({ command }) => command === paths.pgCtl);
    const createdb = commands.find(({ command }) => command === paths.createdb);
    assert.ok(initdb);
    assert.ok(pgCtl);
    assert.ok(createdb);
    assert.ok(initdb.args.includes("--pwfile"));
    assert.ok(initdb.args.includes(paths.postgresPasswordFile));
    assert.doesNotMatch(initdb.args.join(" "), /postgres_URL-safe_secret/);
    assert.deepEqual(pgCtl.args, [
      "start",
      "-D",
      paths.postgresData,
      "-l",
      paths.postgresLog,
      "-w",
    ]);
    assert.equal(createdb.options.env.PGPASSWORD, "postgres_URL-safe_secret");
    assert.doesNotMatch(createdb.args.join(" "), /postgres_URL-safe_secret/);
    assert.equal(existsSync(paths.postgresPasswordFile), false);

    const memuraiConfig = readFileSync(paths.memuraiConfig, "utf8");
    assert.match(memuraiConfig, /^bind 127\.0\.0\.1$/m);
    assert.match(memuraiConfig, /^requirepass memurai_URL-safe_secret$/m);
    assert.match(memuraiConfig, /^save ""$/m);
    assert.match(memuraiConfig, /^appendonly no$/m);
    assert.doesNotMatch(JSON.stringify(result), /postgres_URL-safe_secret|memurai_URL-safe_secret/);
  }));
