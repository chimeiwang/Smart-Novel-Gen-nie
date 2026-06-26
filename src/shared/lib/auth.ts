/**
 * Auth 工具库
 *
 * 提供密码哈希（bcryptjs）、JWT 会话令牌（jose）、httpOnly Cookie 操作。
 * Middleware 不在本文件中，因为 Edge Runtime 需要独立内联 jose 调用。
 */

import { SignJWT, jwtVerify } from "jose";
import bcrypt from "bcryptjs";
import { cookies } from "next/headers";

// ---- 常量 ----

const JWT_SECRET = new TextEncoder().encode(
  process.env.JWT_SECRET ?? "inkforge-default-secret-change-me"
);
const COOKIE_NAME = "inkforge-token";
const SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30; // 30 天

// ---- 密码哈希 ----

export async function hashPassword(password: string): Promise<string> {
  return bcrypt.hash(password, 12);
}

export async function verifyPassword(
  password: string,
  hash: string
): Promise<boolean> {
  return bcrypt.compare(password, hash);
}

// ---- JWT ----

export async function createToken(userId: string): Promise<string> {
  return new SignJWT({ sub: userId })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(`${SESSION_MAX_AGE_SECONDS}s`)
    .sign(JWT_SECRET);
}

export async function verifyToken(
  token: string
): Promise<{ userId: string } | null> {
  try {
    const { payload } = await jwtVerify(token, JWT_SECRET, {
      algorithms: ["HS256"],
    });
    return { userId: payload.sub as string };
  } catch {
    return null;
  }
}

// ---- Cookie 操作 ----

export async function setSessionCookie(token: string): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.set(COOKIE_NAME, token, {
    httpOnly: true,
    secure: false,
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_MAX_AGE_SECONDS,
  });
}

export async function getSessionCookie(): Promise<string | undefined> {
  const cookieStore = await cookies();
  return cookieStore.get(COOKIE_NAME)?.value;
}

export async function deleteSessionCookie(): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.delete(COOKIE_NAME);
}

// ---- Session ----

export async function getSession(): Promise<{ userId: string } | null> {
  const token = await getSessionCookie();
  if (!token) return null;
  return verifyToken(token);
}
