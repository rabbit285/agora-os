import type { Metadata } from "next";

import { SectionHeader } from "@/components/marketing/section-header";

export const metadata: Metadata = {
  title: "About — Veyntra",
  description: "Veyntra is the secure AI operating system for SMEs.",
  alternates: { canonical: "/about" },
};

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6 lg:px-8">
      <SectionHeader eyebrow="About" title="Compliance evidence, without the manual mapping" />
      <div className="mx-auto mt-10 flex max-w-2xl flex-col gap-6 text-sm leading-relaxed text-[var(--fg-muted)]">
        <p>
          Most compliance work is not judgement — it is transcription. Someone reads a policy,
          decides which control it supports, and records that link in a spreadsheet. Multiply
          that by every document and every framework and it becomes a job nobody has time to do
          properly, which is why the evidence trail is usually reconstructed the week before an
          audit. Veyntra exists to do the reading, propose the links, and leave the judgement
          where it belongs — with a person who approves each one.
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
