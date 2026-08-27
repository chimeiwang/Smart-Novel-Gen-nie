/**
 * 页面路由保护。
 *
 * 首页、登录页和法务告知页公开，其余页面要求存在有效会话令牌。业务接口统一由
 * Nginx 转发到核心接口服务，不经过 Next.js。
 */

import { jwtVerify } from "jose";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { resolveSessionSecret } from "./lib/auth/session-secret";

const COOKIE_NAME = "inkforge-token";

export async function proxy(request: NextRequest) {
  const jwtSecret = resolveSessionSecret();
  const { pathname } = request.nextUrl;

  if (pathname === "/" || pathname === "/terms" || pathname === "/privacy") {
    return NextResponse.next();
  }

  if (pathname.startsWith("/login")) {
    // 登录页会通过 Core 的 /auth/me 核对会话对应的用户是否仍然存在。
    // 代理只验证签名会把“签名有效但 Core 已不承认”的旧令牌困在
    // /login 与 /dashboard 的重定向循环里，因此这里必须放行。
    return NextResponse.next();
  }

  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname.includes(".")
  ) {
    return NextResponse.next();
  }

  const token = request.cookies.get(COOKIE_NAME)?.value;
  if (!token) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  try {
    await jwtVerify(token, jwtSecret, { algorithms: ["HS256"] });
    return NextResponse.next();
  } catch {
    const response = NextResponse.redirect(new URL("/login", request.url));
    response.cookies.delete(COOKIE_NAME);
    return response;
  }
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml).*)",
  ],
};
