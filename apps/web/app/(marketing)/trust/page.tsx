import type { Metadata } from "next";
import { FileCheck2, Info, KeyRound, ShieldCheck } from "lucide-react";

import { PageHero } from "@/components/marketing/page-hero";
import { TrustSection } from "@/components/marketing/trust-section";

export const metadata: Metadata = {
  title: "Security & Trust — Veyntra",
  description:
    "How Veyntra approaches tenant isolation, access control, audit logging, and data handling. Built with enterprise security and governance principles.",
  alternates: { canonical: "/trust" },
};

/** Only mechanisms that exist in the codebase are described here. Nothing
 * on this page may become a certification claim — see TrustSection's own
 * note; the disclosure block below is the counterweight that keeps the
 * page honest, so it is styled as a deliberate statement rather than the
 * small grey footnote it used to be. */
const PILLARS = [
  {
    icon: ShieldCheck,
    title: "Tenant isolation",
    description:
      "Every request is scoped to your organization at the API layer, not just the interface — enforced on every read and write, not assumed from the URL.",
  },
  {
    icon: KeyRound,
    title: "Role-based access",
    description:
      "Permissions are granted by role, checked on the server for every action — never a frontend-only restriction.",
  },
  {
    icon: FileCheck2,
    title: "Append-only audit trail",
    description:
      "Sensitive actions are written to an audit log that cannot be edited or deleted after the fact, so the record of what happened stays trustworthy.",
  },
];

export default function TrustPage() {
  return (
    <div>
      <PageHero
        eyebrow="Security & Trust"
        title="Governed by design, not by"
        accent="afterthought"
        description="We don't claim certifications we don't hold. Here's what's actually built into the platform, and where the gaps are today."
      />

      <div className="mx-auto max-w-[var(--content-max-width)] px-4 pb-24 sm:px-6 lg:px-8">
        <div className="mx-auto grid max-w-5xl gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {PILLARS.map((pillar) => (
            <div
              key={pillar.title}
              className="rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-6"
            >
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-[var(--radius-md)] bg-[var(--brand-primary-subtle)]">
                <pillar.icon className="h-5 w-5 text-[var(--brand-primary)]" aria-hidden="true" />
              </span>
              <h2 className="mt-4 text-lg font-semibold text-[var(--fg-default)]">
                {pillar.title}
              </h2>
              <p className="mt-2 text-sm leading-relaxed text-[var(--fg-muted)]">
                {pillar.description}
              </p>
            </div>
          ))}
        </div>

        {/* Given prominence on purpose. A buyer evaluating this page is
            looking for exactly this answer, and burying it in grey
            footnote text reads as hiding it. */}
        <div className="mx-auto mt-12 max-w-3xl rounded-[var(--radius-lg)] border border-[var(--warning-500)]/35 bg-[var(--warning-50)] p-6">
          <p className="flex items-center gap-2 text-sm font-semibold text-[var(--warning-700)]">
            <Info className="h-4 w-4 shrink-0" aria-hidden="true" />
            What we have not done yet
          </p>
          <p className="mt-2 text-sm leading-relaxed text-[var(--warning-700)]">
            Veyntra is built with enterprise security and governance principles. We have not
            completed SOC 2, ISO 27001, or a third-party penetration test at this time — if
            certification status matters for your evaluation, please ask us directly.
          </p>
        </div>
      </div>

      <TrustSection />
    </div>
  );
}
