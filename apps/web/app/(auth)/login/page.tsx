import type { Metadata } from "next";

import { LoginPageClient } from "./login-page-client";

export const metadata: Metadata = {
  title: "Sign in — Agora Origin",
  robots: { index: false, follow: false },
};

export default function LoginPage() {
  return <LoginPageClient />;
}
