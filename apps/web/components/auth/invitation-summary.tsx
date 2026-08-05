import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

export type InvitationSummaryProps = {
  organizationName: string;
  invitedEmail: string;
  roleLabel: string;
  expiresAt: string;
  /** Omitted entirely, never rendered blank, when not safely available. */
  inviterName?: string;
};

/** The invited email and organization are display-only here — the accept
 * flow never lets either be edited client-side (docs/PUBLIC_SITE_DESIGN.md
 * — an invitation's identity is fixed server-side by the token itself). */
export function InvitationSummary({
  organizationName,
  invitedEmail,
  roleLabel,
  expiresAt,
  inviterName,
}: InvitationSummaryProps) {
  return (
    <Card className="bg-[var(--bg-sunken)]">
      <CardContent className="flex flex-col gap-2 pt-5 text-sm">
        <p className="text-[var(--fg-default)]">
          {inviterName ? (
            <>
              <span className="font-medium">{inviterName}</span> invited you to join{" "}
              <span className="font-medium">{organizationName}</span>
            </>
          ) : (
            <>
              You&apos;ve been invited to join <span className="font-medium">{organizationName}</span>
            </>
          )}
        </p>
        <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--fg-muted)]">
          <span>{invitedEmail}</span>
          <Badge variant="secondary">{roleLabel}</Badge>
        </div>
        <p className="text-xs text-[var(--fg-subtle)]">Expires {expiresAt}</p>
      </CardContent>
    </Card>
  );
}
