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
  const initialMode = params?.mode === "register" ? "register" : "login";

  return <LoginForm initialMode={initialMode} />;
}
