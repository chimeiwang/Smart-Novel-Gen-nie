"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { loginAction, registerAction } from "@/app/actions";

export function LoginForm() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [mode, setMode] = useState<"login" | "register">("login");

  const handleSubmit = async (formData: FormData) => {
    setPending(true);
    setError(null);
    try {
      const result = mode === "login"
        ? await loginAction(formData)
        : await registerAction(formData);
      if (result.success) {
        router.push("/");
      } else {
        setError(result.error ?? (mode === "login" ? "登录失败" : "注册失败"));
      }
    } catch {
      setError("网络错误，请重试");
    } finally {
      setPending(false);
    }
  };

  return (
    <main
      className="page stack"
      style={{ alignItems: "center", justifyContent: "center" }}
    >
      <div className="panel" style={{ width: "min(400px, 100%)" }}>
        <div className="panel-header">
          <div>
            <h1 className="title-lg">{mode === "login" ? "登录" : "注册"}</h1>
            <p className="muted" style={{ marginTop: 4 }}>
              {mode === "login" ? "墨铸 InkForge" : "注册即送 1000 积分"}
            </p>
          </div>
        </div>
        <div className="panel-body">
          <form action={handleSubmit} className="stack">
            {error && <div className="notice notice-danger">{error}</div>}
            <label className="stack">
              <span className="label">用户名</span>
              <input
                className="input"
                name="username"
                placeholder="请输入用户名"
                required
                autoComplete="username"
              />
            </label>
            <label className="stack">
              <span className="label">密码</span>
              <input
                className="input"
                type="password"
                name="password"
                placeholder="请输入密码"
                required
                autoComplete="current-password"
              />
            </label>
            {mode === "register" && (
              <label className="stack">
                <span className="label">确认密码</span>
                <input
                  className="input"
                  type="password"
                  name="confirmPassword"
                  placeholder="请再次输入密码"
                  required
                  autoComplete="new-password"
                />
              </label>
            )}
            <button className="button" type="submit" disabled={pending}>
              {pending
                ? (mode === "login" ? "登录中..." : "注册中...")
                : (mode === "login" ? "登录" : "注册并登录")}
            </button>
            <button
              className="button ghost"
              type="button"
              disabled={pending}
              onClick={() => {
                setError(null);
                setMode((value) => value === "login" ? "register" : "login");
              }}
            >
              {mode === "login" ? "没有账号？注册" : "已有账号？登录"}
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
