import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { SignJWT } from "jose";
import { NextRequest } from "next/server";
import { proxy } from "../../../proxy";
import { resolveSessionSecret } from "../../auth/session-secret";

describe("登录页会话核验", () => {
  it("签名有效的旧令牌也交给登录页向 Core 核对", async () => {
    const token = await new SignJWT({})
      .setProtectedHeader({ alg: "HS256" })
      .setSubject("已不存在的用户")
      .setExpirationTime("1h")
      .sign(resolveSessionSecret({ NODE_ENV: "test" }));
    const request = new NextRequest("http://127.0.0.1:43119/login", {
      headers: { cookie: `inkforge-token=${token}` },
    });

    const response = await proxy(request);

    assert.equal(response.headers.get("location"), null);
    assert.equal(response.headers.get("x-middleware-next"), "1");
  });
});
