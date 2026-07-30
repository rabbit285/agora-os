import { VerifyEmailStatus } from "./verify-email-status";

export default async function VerifyEmailPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <VerifyEmailStatus token={token} />;
}
