import { getSession } from "@/shared/lib/auth";
import { redirect } from "next/navigation";
import { LoginForm } from "@/features/auth/login-form";

export default async function LoginPage() {
  const session = await getSession();
  if (session) {
    redirect("/");
  }
  return <LoginForm />;
}
