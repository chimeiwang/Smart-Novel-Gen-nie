import assert from "node:assert/strict";
import test from "node:test";

import { mergeDevelopmentEnv } from "../scripts/dev-env.mjs";

const devDatabase =
  "postgresql+asyncpg://developer:secret@server.example:5432/novelwriterdev";
const devRedis = "redis://:secret@server.example:6379/1";

test("开发数据连接始终使用 .env.local，其他终端变量仍可覆盖文件", () => {
  const result = mergeDevelopmentEnv(
    {
      DATABASE_URL: devDatabase,
      REDIS_URL: devRedis,
      MODEL_PROVIDER: "fake",
    },
    {
      DATABASE_URL: "postgresql+asyncpg://production:secret@server.example:5432/novelwriter",
      REDIS_URL: "redis://:secret@server.example:6379/0",
      MODEL_PROVIDER: "openai_compatible",
    },
  );

  assert.equal(result.DATABASE_URL, devDatabase);
  assert.equal(result.REDIS_URL, devRedis);
  assert.equal(result.MODEL_PROVIDER, "openai_compatible");
});

test("数据连接缺少时不从终端变量回退", () => {
  assert.throws(
    () =>
      mergeDevelopmentEnv(
        { REDIS_URL: devRedis },
        { DATABASE_URL: devDatabase, REDIS_URL: devRedis },
      ),
    /\.env\.local.*DATABASE_URL/,
  );
});
