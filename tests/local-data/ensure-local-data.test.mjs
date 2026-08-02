import assert from "node:assert/strict";
import test from "node:test";

import { runDevelopment } from "../../scripts/dev.mjs";
import { ensureLocalData } from "../../scripts/ensure-local-data.mjs";

const childEnv = {
  DATABASE_URL:
    "postgresql+asyncpg://inkforge_local:local-postgres-password@127.0.0.1:5432/inkforge_local",
  REDIS_URL: "redis://:local-redis-password@127.0.0.1:6379/0",
  PATH: "测试路径",
};

const paths = {
  pgCtl: "C:\\postgres\\pg_ctl.exe",
  pgIsReady: "C:\\postgres\\pg_isready.exe",
  postgresData: "C:\\runtime\\postgres\\data",
  postgresLog: "C:\\runtime\\postgres\\postgres.log",
  memuraiCli: "C:\\Program Files\\Memurai\\memurai-cli.exe",
  memuraiConfig: "C:\\runtime\\memurai\\memurai.conf",
  memuraiExe: "C:\\Program Files\\Memurai\\memurai.exe",
  memuraiRoot: "C:\\runtime\\memurai",
};

function createRuntime({
  postgresOpen = true,
  postgresHealthy = true,
  redisOpen = true,
  redisHealthy = true,
} = {}) {
  const state = { postgresOpen, postgresHealthy, redisOpen, redisHealthy };
  const commands = [];
  const detachedStarts = [];

  return {
    commands,
    detachedStarts,
    options: {
      paths,
      fileExists: () => true,
      isPortOpen: async (_host, port) => (port === 5432 ? state.postgresOpen : state.redisOpen),
      runCommand(command, args, options) {
        commands.push({ command, args, options });
        if (command === paths.pgCtl) {
          state.postgresOpen = true;
          state.postgresHealthy = true;
          return { status: 0, stdout: "", stderr: "" };
        }
        if (command === paths.pgIsReady) {
          return { status: state.postgresHealthy ? 0 : 1, stdout: "", stderr: "" };
        }
        if (command === paths.memuraiCli) {
          return {
            status: state.redisHealthy ? 0 : 1,
            stdout: state.redisHealthy ? "PONG\r\n" : "",
            stderr: "",
          };
        }
        throw new Error(`未预期命令：${command}`);
      },
      spawnDetached(command, args, options) {
        detachedStarts.push({ command, args, options });
        state.redisOpen = true;
        state.redisHealthy = true;
        return { on() {}, unref() {} };
      },
      delay: async () => {},
      timeoutMs: 20,
    },
  };
}

test("PostgreSQL 和 Memurai 均健康时不启动任何服务", async () => {
  const runtime = createRuntime();

  await ensureLocalData(childEnv, runtime.options);

  assert.equal(runtime.commands.filter(({ command }) => command === paths.pgCtl).length, 0);
  assert.equal(runtime.detachedStarts.length, 0);
});

test("只有 PostgreSQL 停止时仅通过 pg_ctl 启动 PostgreSQL", async () => {
  const runtime = createRuntime({ postgresOpen: false, postgresHealthy: false });

  await ensureLocalData(childEnv, runtime.options);

  const starts = runtime.commands.filter(({ command }) => command === paths.pgCtl);
  assert.equal(starts.length, 1);
  assert.deepEqual(starts[0].args, [
    "start",
    "-D",
    paths.postgresData,
    "-l",
    paths.postgresLog,
    "-w",
  ]);
  assert.equal(runtime.detachedStarts.length, 0);
});

test("只有 Memurai 停止时仅以脱离方式启动 Memurai", async () => {
  const runtime = createRuntime({ redisOpen: false, redisHealthy: false });

  await ensureLocalData(childEnv, runtime.options);

  assert.equal(runtime.commands.filter(({ command }) => command === paths.pgCtl).length, 0);
  assert.equal(runtime.detachedStarts.length, 1);
  assert.equal(runtime.detachedStarts[0].command, paths.memuraiExe);
  assert.deepEqual(runtime.detachedStarts[0].args, [paths.memuraiConfig]);
  assert.deepEqual(
    {
      detached: runtime.detachedStarts[0].options.detached,
      stdio: runtime.detachedStarts[0].options.stdio,
      windowsHide: runtime.detachedStarts[0].options.windowsHide,
    },
    { detached: true, stdio: "ignore", windowsHide: true },
  );
});

test("5432 已占用但 PostgreSQL 健康检查失败时拒绝接管", async () => {
  const runtime = createRuntime({ postgresHealthy: false });

  await assert.rejects(
    () => ensureLocalData(childEnv, runtime.options),
    /5432.*健康检查失败.*不会停止或接管/,
  );
  assert.equal(runtime.commands.filter(({ command }) => command === paths.pgCtl).length, 0);
  assert.equal(runtime.detachedStarts.length, 0);
});

test("6379 已占用但 Memurai PING 失败时拒绝接管", async () => {
  const runtime = createRuntime({ redisHealthy: false });

  await assert.rejects(
    () => ensureLocalData(childEnv, runtime.options),
    /6379.*PING 失败.*不会停止或接管/,
  );
  assert.equal(runtime.commands.filter(({ command }) => command === paths.pgCtl).length, 0);
  assert.equal(runtime.detachedStarts.length, 0);
});

test("健康检查仅通过子进程环境传递密码", async () => {
  const runtime = createRuntime();

  await ensureLocalData(childEnv, runtime.options);

  const postgresCheck = runtime.commands.find(({ command }) => command === paths.pgIsReady);
  const redisCheck = runtime.commands.find(({ command }) => command === paths.memuraiCli);
  assert.equal(postgresCheck.options.env.PGPASSWORD, "local-postgres-password");
  assert.equal(redisCheck.options.env.REDISCLI_AUTH, "local-redis-password");
  assert.doesNotMatch(postgresCheck.args.join(" "), /local-postgres-password/);
  assert.doesNotMatch(redisCheck.args.join(" "), /local-redis-password/);
});

test("本地数据门卫失败时 dev 不创建应用进程", async () => {
  let spawnCount = 0;
  const completeEnv = {
    ...childEnv,
    JWT_SECRET: "测试会话密钥",
    npm_execpath: "C:\\tools\\npm-cli.js",
    CORE_SERVICE_PRIVATE_KEY_PATH: "infra/secrets/core-private.pem",
    AGENT_SERVICE_PUBLIC_KEY_PATH: "infra/secrets/agent-public.json",
    CORE_SERVICE_PUBLIC_KEY_PATH: "infra/secrets/core-public.json",
    AGENT_SERVICE_PRIVATE_KEY_PATH: "infra/secrets/agent-private.pem",
  };

  await assert.rejects(
    () =>
      runDevelopment({
        root: "C:\\workspace\\inkforge",
        parentEnv: completeEnv,
        loadEnv: () => ({ ...completeEnv }),
        ensureData: async () => {
          throw new Error("本地数据未就绪");
        },
        fileExists: () => true,
        makeDirectory: () => {},
        spawnProcess: () => {
          spawnCount += 1;
          throw new Error("不应创建应用进程");
        },
      }),
    /本地数据未就绪/,
  );
  assert.equal(spawnCount, 0);
});
