import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

export default async function ComingSoonPage({
  searchParams,
}: {
  searchParams: Promise<{ module?: string }>;
}) {
  const { module } = await searchParams;
  const label = module ? module.charAt(0).toUpperCase() + module.slice(1) : "This module";

  return (
    <div className="mx-auto max-w-xl py-16">
      <Card>
        <CardHeader>
          <CardTitle>{label} isn&apos;t built yet</CardTitle>
          <CardDescription>
            This is Phase 1 of a multi-phase build (see docs/IMPLEMENTATION_PLAN.md). The
            platform foundation — auth, organizations, tasks, approvals, and the AI gateway — is
            in place; this module ships in a later phase.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-neutral-500">
          Nothing here is a working page yet, intentionally — see spec section 82 (&quot;No Fake
          Features&quot;) for why this state is shown instead of a broken link or placeholder
          data.
        </CardContent>
      </Card>
    </div>
  );
}
