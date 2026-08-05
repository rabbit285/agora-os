import { CheckCircle2 } from "lucide-react";

import { SectionHeader } from "@/components/marketing/section-header";

const TRUST_ITEMS = [
  "Tenant isolation on every request",
  "Role-based access control",
  "Append-only audit logging",
  "Human-reviewable approval workflows",
  "Data provenance on every record",
  "Provider transparency — no hidden data sharing",
  "Read-only integration options",
  "Configurable, per-role permissions",
  "Customer-controlled connections",
];

/** No certification claims (SOC 2 / ISO 27001 / GDPR / pen-test status) —
 * this codebase has none, so none are claimed. "Built with enterprise
 * security and governance principles" is the honest, brief-specified
 * framing; "fully certified" or "guaranteed compliant" never appear. */
export function TrustSection() {
  return (
    <section className="border-y border-[var(--border-default)] bg-[var(--bg-sunken)]">
      <div className="mx-auto max-w-[var(--content-max-width)] px-4 py-20 sm:px-6 lg:px-8">
        <SectionHeader
          eyebrow="Trust and governance"
          title="Built with enterprise security and governance principles"
          description="Every action is permission-aware, reviewable, and auditable — control stays with your organization."
        />
        <ul className="mx-auto mt-10 grid max-w-3xl gap-x-8 gap-y-3 sm:grid-cols-2">
          {TRUST_ITEMS.map((item) => (
            <li key={item} className="flex items-start gap-2.5 text-sm text-[var(--fg-muted)]">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[var(--success-600)]" aria-hidden="true" />
              {item}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
