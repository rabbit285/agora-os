import type { Metadata } from "next";

import { VerifyEmailStatus } from "./verify-email-status";

export const metadata: Metadata = {
  title: "Verify email — Agora Origin",
  robots: { index: false, follow: false },
};

export default async function VerifyEmailPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <VerifyEmailStatus token={token} />;
}
