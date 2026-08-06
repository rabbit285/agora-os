import type { Metadata } from "next";

import { ForgotPasswordClient } from "./forgot-password-client";

export const metadata: Metadata = {
  title: "Reset your password — Agora Origin",
  robots: { index: false, follow: false },
};

export default function ForgotPasswordPage() {
  return <ForgotPasswordClient />;
}
