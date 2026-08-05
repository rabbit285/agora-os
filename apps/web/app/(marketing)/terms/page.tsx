import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Terms of Service — Agora Origin",
  description: "The terms that govern use of Agora Origin.",
  alternates: { canonical: "/terms" },
};

export default function TermsPage() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-16 sm:px-6 lg:px-8">
      <h1 className="text-2xl font-semibold text-[var(--fg-default)]">Terms of Service</h1>
      <p className="mt-2 text-xs text-[var(--fg-subtle)]">Last updated: August 2026</p>

      <div className="mt-8 flex flex-col gap-6 text-sm leading-relaxed text-[var(--fg-muted)]">
        <section>
          <h2 className="text-base font-semibold text-[var(--fg-default)]">Your account</h2>
          <p className="mt-2">
            You&apos;re responsible for the accuracy of the information you provide and for
            activity that occurs under your account. Access to your workspace is governed by the
            role-based permissions you or your organization&apos;s administrator configure.
          </p>
        </section>
        <section>
          <h2 className="text-base font-semibold text-[var(--fg-default)]">Acceptable use</h2>
          <p className="mt-2">
            Agora Origin is provided for legitimate business use. You may not use it to store or
            process data you don&apos;t have the right to process, or to attempt to access
            another organization&apos;s workspace.
          </p>
        </section>
        <section>
          <h2 className="text-base font-semibold text-[var(--fg-default)]">Plans and billing</h2>
          <p className="mt-2">
            The Starter plan is free. Growth, Business, and Enterprise plans are arranged
            directly with our team. Plan entitlements are described on our{" "}
            <Link href="/pricing" className="underline hover:text-[var(--fg-default)]">
              Pricing
            </Link>{" "}
            page.
          </p>
        </section>
        <section>
          <h2 className="text-base font-semibold text-[var(--fg-default)]">Changes</h2>
          <p className="mt-2">
            We may update these terms from time to time. Material changes will be reflected here
            with an updated date.
          </p>
        </section>
        <section>
          <h2 className="text-base font-semibold text-[var(--fg-default)]">Contact</h2>
          <p className="mt-2">
            Questions about these terms can be sent through our{" "}
            <Link href="/contact" className="underline hover:text-[var(--fg-default)]">
              contact form
            </Link>
            .
          </p>
        </section>
      </div>
    </div>
  );
}
