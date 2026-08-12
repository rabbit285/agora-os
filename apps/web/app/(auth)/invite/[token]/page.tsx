import type { Metadata } from "next";

import { AcceptInvitationForm } from "./accept-invitation-form";

export const metadata: Metadata = {
  title: "Accept invitation — Veyntra",
  robots: { index: false, follow: false },
};

export default async function InvitePage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <AcceptInvitationForm token={token} />;
}
