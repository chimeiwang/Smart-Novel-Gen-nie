import assert from "node:assert/strict";
import { createServer } from "node:net";
import { describe, it } from "node:test";

import {
  findOccupiedPorts,
  isSupportedNodeVersion,
  LOCAL_DEVELOPMENT_PORTS,
} from "./dev-preflight.mjs";

describe("本地开发启动预检", () => {
  it("拒绝低于 20.12 的 Node 并接受新版本", () => {
    assert.equal(isSupportedNodeVersion("20.11.1"), false);
    assert.equal(isSupportedNodeVersion("20.12.0"), true);
    assert.equal(isSupportedNodeVersion("22.17.1"), true);
  });

  it("预检端口与统一启动器使用的服务端口一致", () => {
    assert.deepEqual(LOCAL_DEVELOPMENT_PORTS, {
      web: 43119,
      coreApi: 8000,
      agentService: 8001,
    });
  });

  it("能识别已占用端口", async () => {
    const server = createServer();
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    const address = server.address();
    assert.equal(typeof address, "object");
    const port = address.port;
    try {
      assert.deepEqual(await findOccupiedPorts([port]), [port]);
    } finally {
      await new Promise((resolve) => server.close(resolve));
    }
  });
});
