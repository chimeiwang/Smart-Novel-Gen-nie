"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { browserApi } from "@/lib/api/browser";
import { createClientRequestId } from "@/lib/api/client-request-id";
import { ApiResponseError, requireApiData } from "@/lib/api/response";

import "./login-form.css";

const CAPTCHA_SCRIPT_ID = "inkforge-aliyun-captcha-script";
const CAPTCHA_SCRIPT_URL =
  "https://o.alicdn.com/captcha-frontend/aliyunCaptcha/AliyunCaptcha.js";
const CAPTCHA_ELEMENT_ID = "inkforge-captcha-element";
const CAPTCHA_BUTTON_ID = "inkforge-captcha-trigger";

let captchaScriptPromise: Promise<void> | null = null;

type AuthMode = "phone" | "legacy-login" | "legacy-register";

interface PhoneAuthConfig {
  prefix: string;
  sceneId: string;
  consentVersion: string;
}

interface LoginFormProps {
  initialMode: AuthMode;
  phoneAuth: PhoneAuthConfig | null;
}

interface AliyunCaptchaWindow extends Window {
  AliyunCaptchaConfig?: {
    region: "cn";
    prefix: string;
  };
  initAliyunCaptcha?: (options: {
    SceneId: string;
    mode: "popup";
    element: string;
    button: string;
    success: (captchaVerifyParam: string) => void;
    fail?: () => void;
    getInstance: (instance: unknown) => void;
    onError?: () => void;
    onClose?: (reason: string) => void;
    slideStyle: { width: number; height: number };
    language: "cn";
    delayBeforeSuccess: boolean;
  }) => void;
}

function loadAliyunCaptcha(prefix: string): Promise<void> {
  const captchaWindow = window as AliyunCaptchaWindow;
  captchaWindow.AliyunCaptchaConfig = { region: "cn", prefix };
  if (typeof captchaWindow.initAliyunCaptcha === "function") {
    return Promise.resolve();
  }
  if (captchaScriptPromise) return captchaScriptPromise;

  captchaScriptPromise = new Promise<void>((resolve, reject) => {
    const existing = document.getElementById(CAPTCHA_SCRIPT_ID) as HTMLScriptElement | null;
    const script = existing ?? document.createElement("script");
    const loaded = () => {
      if (typeof captchaWindow.initAliyunCaptcha === "function") resolve();
      else reject(new Error("人机验证组件未正确加载"));
    };
    const failed = () => reject(new Error("人机验证组件加载失败"));
    script.addEventListener("load", loaded, { once: true });
    script.addEventListener("error", failed, { once: true });
    if (!existing) {
      script.id = CAPTCHA_SCRIPT_ID;
      script.src = CAPTCHA_SCRIPT_URL;
      script.async = true;
      document.head.appendChild(script);
    }
  }).catch((error) => {
    captchaScriptPromise = null;
    throw error;
  });
  return captchaScriptPromise;
}

export function LoginForm({ initialMode, phoneAuth }: LoginFormProps) {
  const router = useRouter();
  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<
    "legacy" | "captcha" | "send" | "verify" | null
  >(null);
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [challengeId, setChallengeId] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);
  const [captchaReady, setCaptchaReady] = useState(false);
  const [captchaEpoch, setCaptchaEpoch] = useState(0);
  const sendRequestId = useRef(createClientRequestId());
  const verifyRequestId = useRef(createClientRequestId());
  const captchaSuccess = useRef<(captchaVerifyParam: string) => void>(() => {});

  const sendChallenge = useCallback(async (captchaVerifyParam: string) => {
    if (!phoneAuth) return;
    if (!acceptedTerms) {
      setCaptchaReady(false);
      setCaptchaEpoch((value) => value + 1);
      setPending(null);
      setError("请先阅读并同意用户协议和隐私政策");
      return;
    }
    setCaptchaReady(false);
    setPending("send");
    setError(null);
    try {
      const result = requireApiData(await browserApi.POST(
        "/api/v1/auth/phone/challenges",
        {
          body: {
            phone,
            captchaVerifyParam,
            consentVersion: phoneAuth.consentVersion,
            acceptedTerms: true,
            clientRequestId: sendRequestId.current,
          },
        },
      ));
      setChallengeId(result.challengeId);
      setCooldown(result.resendAfterSeconds);
      setCode("");
      verifyRequestId.current = createClientRequestId();
      sendRequestId.current = createClientRequestId();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "验证码发送失败，请重试");
    } finally {
      setPending(null);
      // V3 的 CaptchaVerifyParam 只能使用一次；每次业务请求结束后都重新初始化。
      setCaptchaEpoch((value) => value + 1);
    }
  }, [acceptedTerms, phone, phoneAuth]);

  useEffect(() => {
    captchaSuccess.current = (captchaVerifyParam) => {
      void sendChallenge(captchaVerifyParam);
    };
  }, [sendChallenge]);

  useEffect(() => {
    if (!phoneAuth) return;
    let active = true;
    let readyTimer: ReturnType<typeof setTimeout> | null = null;
    void loadAliyunCaptcha(phoneAuth.prefix)
      .then(() => {
        if (!active) return;
        const captchaWindow = window as AliyunCaptchaWindow;
        captchaWindow.initAliyunCaptcha?.({
          SceneId: phoneAuth.sceneId,
          mode: "popup",
          element: `#${CAPTCHA_ELEMENT_ID}`,
          button: `#${CAPTCHA_BUTTON_ID}`,
          success: (captchaVerifyParam) => {
            if (!active || !captchaVerifyParam) return;
            captchaSuccess.current(captchaVerifyParam);
          },
          fail: () => {},
          getInstance: () => {
            if (!active) return;
            // 阿里云建议初始化与首次验证至少间隔两秒，以完成风控资源加载。
            readyTimer = setTimeout(() => {
              if (active) setCaptchaReady(true);
            }, 2_000);
          },
          onError: () => {
            if (!active) return;
            setPending(null);
            setError("人机验证暂时不可用，请刷新页面后重试");
          },
          onClose: (reason) => {
            if (active && reason === "userDismiss") setPending(null);
          },
          slideStyle: { width: 360, height: 40 },
          language: "cn",
          delayBeforeSuccess: false,
        });
      })
      .catch(() => {
        if (!active) return;
        setPending(null);
        setError("人机验证组件加载失败，请刷新页面后重试");
      });
    return () => {
      active = false;
      if (readyTimer) clearTimeout(readyTimer);
    };
  }, [captchaEpoch, phoneAuth]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown((value) => Math.max(0, value - 1)), 1_000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  const requestSmsCode = () => {
    setError(null);
    if (!/^1[3-9][0-9]{9}$/.test(phone)) {
      setError("请输入正确的 11 位中国大陆手机号");
      return;
    }
    if (!acceptedTerms) {
      setError("请先阅读并同意用户协议和隐私政策");
      return;
    }
    if (!captchaReady) {
      setError("安全验证仍在加载，请稍后再试");
      return;
    }
    setPending("captcha");
    document.getElementById(CAPTCHA_BUTTON_ID)?.click();
  };

  const verifyPhone = async () => {
    if (!challengeId || !/^\d{6}$/.test(code)) {
      setError("请输入 6 位短信验证码");
      return;
    }
    setPending("verify");
    setError(null);
    try {
      const result = requireApiData(await browserApi.POST(
        "/api/v1/auth/phone/challenges/{challenge_id}/verify",
        {
          params: { path: { challenge_id: challengeId } },
          body: {
            phone,
            code,
            clientRequestId: verifyRequestId.current,
          },
        },
      ));
      router.push(result.isNewUser ? "/dashboard?welcome=1" : "/dashboard");
      router.refresh();
    } catch (caught) {
      if (caught instanceof ApiResponseError && caught.code === "INVALID_SMS_CODE") {
        verifyRequestId.current = createClientRequestId();
      }
      setError(caught instanceof Error ? caught.message : "手机号登录失败，请重试");
    } finally {
      setPending(null);
    }
  };

  const submitLegacy = async (formData: FormData) => {
    setPending("legacy");
    setError(null);
    try {
      const username = String(formData.get("username") ?? "");
      const password = String(formData.get("password") ?? "");
      const result = mode === "legacy-register"
        ? await browserApi.POST("/api/v1/auth/register", {
            body: {
              username,
              password,
              confirmPassword: String(formData.get("confirmPassword") ?? ""),
            },
          })
        : await browserApi.POST("/api/v1/auth/login", { body: { username, password } });
      requireApiData(result);
      router.push("/dashboard");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "网络错误，请重试");
    } finally {
      setPending(null);
    }
  };

  const switchMode = (nextMode: AuthMode) => {
    setError(null);
    setPending(null);
    setMode(nextMode);
  };

  const changePhone = () => {
    setChallengeId(null);
    setCode("");
    setCooldown(0);
    sendRequestId.current = createClientRequestId();
    verifyRequestId.current = createClientRequestId();
  };

  const isPhoneMode = mode === "phone" && phoneAuth !== null;
  const isLegacyRegister = mode === "legacy-register";

  return (
    <main className="auth-page">
      {phoneAuth && (
        <>
          <div id={CAPTCHA_ELEMENT_ID} className="aliyun-captcha-element" />
          <button
            id={CAPTCHA_BUTTON_ID}
            className="aliyun-captcha-trigger"
            type="button"
            tabIndex={-1}
            aria-hidden="true"
          />
        </>
      )}
      <section className="panel auth-panel" aria-labelledby="auth-title">
        <div className="panel-header auth-header">
          <div>
            <div className="auth-brand">墨铸 · InkForge</div>
            <h1 id="auth-title" className="title-lg">
              {isPhoneMode
                ? "手机号登录"
                : isLegacyRegister ? "创建账号" : "原账号登录"}
            </h1>
            <p className="muted auth-subtitle">
              {isPhoneMode
                ? "未注册手机号验证后将自动创建账号，并赠送 1000 积分"
                : isLegacyRegister
                  ? "注册即送 1000 积分"
                  : phoneAuth
                    ? "原用户名和密码仍可直接登录，无需绑定手机号"
                    : "使用原用户名和密码继续登录"}
            </p>
          </div>
        </div>
        <div className="panel-body auth-body">
          {phoneAuth && (
            <div className="auth-method-switch" role="tablist" aria-label="登录方式">
              <button
                id="auth-method-phone"
                className="auth-method-option"
                type="button"
                role="tab"
                aria-selected={isPhoneMode}
                aria-controls="auth-phone-panel"
                disabled={pending !== null}
                onClick={() => switchMode("phone")}
              >
                手机号登录
              </button>
              <button
                id="auth-method-legacy"
                className="auth-method-option"
                type="button"
                role="tab"
                aria-selected={!isPhoneMode}
                aria-controls="auth-legacy-panel"
                disabled={pending !== null}
                onClick={() => switchMode("legacy-login")}
              >
                原账号登录
              </button>
            </div>
          )}
          {error && <div className="notice notice-danger" role="alert">{error}</div>}

          {isPhoneMode ? (
            <form
              id="auth-phone-panel"
              action={verifyPhone}
              className="stack auth-form"
              role="tabpanel"
              aria-labelledby="auth-method-phone"
            >
              <div className="auth-legacy-warning">
                <strong>已有原用户名账号？</strong>
                <span>
                  请切换到“原账号登录”。手机号不会自动绑定旧账号；改用新手机号会创建独立账号，原作品和积分不会迁移。
                </span>
              </div>
              <label className="stack">
                <span className="label">手机号</span>
                <div className="auth-phone-row">
                  <span className="auth-country-code">+86</span>
                  <input
                    className="input"
                    name="phone"
                    value={phone}
                    onChange={(event) => setPhone(event.target.value.replace(/\D/g, "").slice(0, 11))}
                    placeholder="请输入 11 位手机号"
                    inputMode="numeric"
                    autoComplete="tel-national"
                    disabled={challengeId !== null}
                    required
                  />
                  {challengeId && (
                    <button
                      className="button ghost sm"
                      type="button"
                      onClick={changePhone}
                      disabled={pending !== null}
                    >
                      更换
                    </button>
                  )}
                </div>
              </label>
              <label className="stack">
                <span className="label">短信验证码</span>
                <div className="auth-code-row">
                  <input
                    className="input"
                    name="code"
                    value={code}
                    onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                    placeholder="6 位验证码"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    disabled={!challengeId}
                    required
                  />
                  <button
                    className="button secondary auth-send-button"
                    type="button"
                    onClick={requestSmsCode}
                    disabled={pending !== null || cooldown > 0}
                  >
                    {pending === "captcha"
                      ? "请完成验证"
                      : pending === "send"
                        ? "发送中..."
                        : cooldown > 0
                          ? `${cooldown} 秒后重发`
                          : captchaReady ? (challengeId ? "重新发送" : "获取验证码") : "安全验证加载中"}
                  </button>
                </div>
              </label>
              <label className="auth-consent">
                <input
                  type="checkbox"
                  checked={acceptedTerms}
                  onChange={(event) => setAcceptedTerms(event.target.checked)}
                />
                <span>
                  我已阅读并同意 <Link href="/terms" target="_blank">用户协议</Link> 和{" "}
                  <Link href="/privacy" target="_blank">隐私政策</Link>
                </span>
              </label>
              <button
                className="button auth-primary"
                type="submit"
                disabled={!challengeId || code.length !== 6 || pending !== null}
              >
                {pending === "verify" ? "登录中..." : "验证并登录"}
              </button>
            </form>
          ) : (
            <form
              id="auth-legacy-panel"
              action={submitLegacy}
              className="stack auth-form"
              role={phoneAuth ? "tabpanel" : undefined}
              aria-labelledby={phoneAuth ? "auth-method-legacy" : undefined}
            >
              {phoneAuth && (
                <div className="auth-note">
                  <strong>原账号无需绑定手机号</strong>
                  <span>继续使用原用户名和密码登录，原作品和积分保持不变。</span>
                </div>
              )}
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
                  autoComplete={isLegacyRegister ? "new-password" : "current-password"}
                />
              </label>
              {isLegacyRegister && (
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
              <button className="button auth-primary" type="submit" disabled={pending !== null}>
                {pending === "legacy"
                  ? (isLegacyRegister ? "创建中..." : "登录中...")
                  : (isLegacyRegister ? "注册并登录" : phoneAuth ? "登录原账号" : "登录")}
              </button>
              {!phoneAuth && (
                <button
                  className="button ghost"
                  type="button"
                  disabled={pending !== null}
                  onClick={() => switchMode(isLegacyRegister ? "legacy-login" : "legacy-register")}
                >
                  {isLegacyRegister ? "已有账号？登录" : "没有账号？注册"}
                </button>
              )}
            </form>
          )}
        </div>
      </section>
    </main>
  );
}
