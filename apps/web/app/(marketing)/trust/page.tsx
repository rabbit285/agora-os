import type { Metadata } from "next";
import { KeyRound, ShieldCheck } from "lucide-react";

import { SectionHeader } from "@/components/marketing/section-header";
import { TrustSection } from "@/components/marketing/trust-section";

export const metadata: Metadata = {
  title: "Security & Trust — Agora Origin",
  description:
    "How Agora Origin approaches tenant isolation, access control, audit logging, and data handling. Built with enterprise security and governance principles.",
  alternates: { canonical: "/trust" },
};

export default function TrustPage() {
  return (
    <div>
      <div className="mx-auto max-w-[var(--content-max-width)] px-4 py-16 sm:px-6 lg:px-8">
        <SectionHeader
          eyebrow="Security & Trust"
          title="Governed by design, not by afterthought"
          description="We don't claim certifications we don't hold. Here's what's actually built into the platform, and where the gaps are today."
        />

        <div className="mx-auto mt-14 grid max-w-3xl gap-6 sm:grid-cols-2">
          <div className="flex gap-3">
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-[var(--brand-primary)]" aria-hidden="true" />
            <div>
              <h2 className="text-sm font-semibold text-[var(--fg-default)]">Tenant isolation</h2>
              <p className="mt-1 text-sm leading-relaxed text-[var(--fg-muted)]">
                Every request is scoped to your organization at the API layer, not just the
                interface — enforced on every read and write, not assumed from the URL.
              </p>
            </div>
          </div>
          <div className="flex gap-3">
            <KeyRound className="mt-0.5 h-5 w-5 shrink-0 text-[var(--brand-primary)]" aria-hidden="true" />
            <div>
              <h2 className="text-sm font-semibold text-[var(--fg-default)]">Role-based access</h2>
              <p className="mt-1 text-sm leading-relaxed text-[var(--fg-muted)]">
                Permissions are granted by role, checked on the server for every action — never a
                frontend-only restriction.
              </p>
            </div>
          </div>
        </div>

        <p className="mx-auto mt-12 max-w-2xl text-center text-sm text-[var(--fg-muted)]">
          Agora Origin is built with enterprise security and governance principles. We have not
          completed SOC 2, ISO 27001, or a third-party penetration test at this time — if
          certification status matters for your evaluation, please ask us directly.
        </p>
      </div>

      <TrustSection />
    </div>
  );
}
