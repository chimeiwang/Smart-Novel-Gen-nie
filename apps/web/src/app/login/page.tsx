import { redirect } from "next/navigation";
import { LoginForm } from "@/features/auth/login-form";
import { createServerApiClient } from "@/lib/api/server";

export default async function LoginPage({
  searchParams,
}: {
  searchParams?: Promise<{ mode?: string }>;
}) {
  const client = await createServerApiClient();
  const { data: currentUser } = await client.GET("/api/v1/auth/me");
  if (currentUser) {
    redirect("/dashboard");
  }

  const params = await searchParams;
  const phoneAuthEnabled = process.env.PHONE_AUTH_ENABLED === "true"
    && process.env.PHONE_AUTH_SEND_ENABLED === "true";
  const captchaPrefix = process.env.ALIYUN_CAPTCHA_PREFIX?.trim();
  const captchaSceneId = process.env.ALIYUN_CAPTCHA_SCENE_ID?.trim();
  const phoneAuth = phoneAuthEnabled && captchaPrefix && captchaSceneId
    ? {
        prefix: captchaPrefix,
        sceneId: captchaSceneId,
        consentVersion: process.env.PHONE_AUTH_CONSENT_VERSION?.trim() || "2026-08-27",
      }
    : null;
  const initialMode = phoneAuth
    ? (params?.mode === "legacy" ? "legacy-login" : "phone")
    : (params?.mode === "register" ? "legacy-register" : "legacy-login");

  return <LoginForm initialMode={initialMode} phoneAuth={phoneAuth} />;
}
