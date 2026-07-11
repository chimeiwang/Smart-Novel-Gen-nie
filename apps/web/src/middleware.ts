/**
 * Middleware — 路由保护
 *
 * 公开路由 / 放行；/login 放行（已登录则重定向 /dashboard）。
 * /_next/*、/api/*、静态资源放行。
 * 其他路由检查 session cookie，无效则重定向 /login。
 *
 * 使用 jose 直接操作（不导入 auth.ts），兼容 Edge Runtime。
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { jwtVerify } from "jose";

const JWT_SECRET = new TextEncoder().encode(
  process.env.JWT_SECRET ?? "inkforge-default-secret-change-me"
);
const COOKIE_NAME = "inkforge-token";

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // 官网首页公开放行。
  if (pathname === "/") {
    return NextResponse.next();
  }

  // 登录页：已登录 → 重定向到工作台首页，未登录 → 放行
  if (pathname.startsWith("/login")) {
    const token = request.cookies.get(COOKIE_NAME)?.value;
    if (token) {
      try {
        await jwtVerify(token, JWT_SECRET, { algorithms: ["HS256"] });
        return NextResponse.redirect(new URL("/dashboard", request.url));
      } catch {
        // token 无效，放行到登录页
      }
    }
    return NextResponse.next();
  }

  // Next.js 内部路径 + API + 静态资源放行
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname.includes(".")
  ) {
    return NextResponse.next();
  }

  // 其他路由：检查 token
  const token = request.cookies.get(COOKIE_NAME)?.value;
  if (!token) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  try {
    await jwtVerify(token, JWT_SECRET, { algorithms: ["HS256"] });
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
