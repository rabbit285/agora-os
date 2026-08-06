import type { Metadata } from "next";

import { SignupPageClient } from "./signup-page-client";

export const metadata: Metadata = {
  title: "Start free — Agora Origin",
  robots: { index: false, follow: false },
};

export default function SignupPage() {
  return <SignupPageClient />;
}
