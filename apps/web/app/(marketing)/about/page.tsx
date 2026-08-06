import type { Metadata } from "next";

import { SectionHeader } from "@/components/marketing/section-header";

export const metadata: Metadata = {
  title: "About — Agora Origin",
  description: "Agora Origin is the secure AI operating system for European SMEs.",
  alternates: { canonical: "/about" },
};

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6 lg:px-8">
      <SectionHeader eyebrow="About" title="The secure AI operating system for European SMEs" />
      <div className="mx-auto mt-10 flex max-w-2xl flex-col gap-6 text-sm leading-relaxed text-[var(--fg-muted)]">
        <p>
          Growing businesses accumulate tools faster than they can govern them. Compliance lives
          in spreadsheets, security findings live in a separate dashboard, sales data lives in a
          CRM nobody fully trusts, and support tickets live somewhere else entirely. Agora Origin
          exists to bring that back into one governed workspace — not by replacing every tool you
          already use, but by connecting them and adding the compliance, security, and
          automation layer most growing companies don&apos;t have time to build themselves.
        </p>
        <p>
          We build for organizations that need practical AI with governance, visibility, and
          control — not AI that acts on its own. Every sensitive action stays permission-aware,
          reviewable, and auditable, because that&apos;s what makes AI usable inside a regulated
          or security-conscious business, not despite the regulation but because of it.
        </p>
        <p>
          We&apos;re building this for teams of roughly 20 to 200 people, across compliance-heavy and
          security-conscious industries — but the platform is not limited to any one sector.
        </p>
      </div>
    </div>
  );
}
