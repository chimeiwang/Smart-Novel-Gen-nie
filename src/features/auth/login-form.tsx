"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { loginAction } from "@/app/actions";

export function LoginForm() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const handleSubmit = async (formData: FormData) => {
    setPending(true);
    setError(null);
    try {
      const result = await loginAction(formData);
      if (result.success) {
        router.push("/");
      } else {
        setError(result.error ?? "登录失败");
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
          <h1 className="title-lg">登录</h1>
          <p className="muted" style={{ marginTop: 4 }}>
            智能小说创作工具
          </p>
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
            <button className="button" type="submit" disabled={pending}>
              {pending ? "登录中..." : "登录"}
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
