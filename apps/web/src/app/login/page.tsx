import { getSession } from "@/shared/lib/auth";
import { redirect } from "next/navigation";
import { LoginForm } from "@/features/auth/login-form";

export default async function LoginPage({
  searchParams,
}: {
  searchParams?: Promise<{ mode?: string }>;
}) {
  const session = await getSession();
  if (session) {
    redirect("/dashboard");
  }

  const params = await searchParams;
  const initialMode = params?.mode === "register" ? "register" : "login";

  return <LoginForm initialMode={initialMode} />;
}
