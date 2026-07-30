import { AcceptInvitationForm } from "./accept-invitation-form";

export default async function InvitePage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <AcceptInvitationForm token={token} />;
}
