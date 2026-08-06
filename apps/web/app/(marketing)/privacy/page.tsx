import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy Policy — Agora Origin",
  description: "How Agora Origin collects, uses, and protects your data.",
  alternates: { canonical: "/privacy" },
};

export default function PrivacyPage() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-16 sm:px-6 lg:px-8">
      <h1 className="text-2xl font-semibold text-[var(--fg-default)]">Privacy Policy</h1>
      <p className="mt-2 text-xs text-[var(--fg-muted)]">Last updated: August 2026</p>

      <div className="mt-8 flex flex-col gap-6 text-sm leading-relaxed text-[var(--fg-muted)]">
        <section>
          <h2 className="text-base font-semibold text-[var(--fg-default)]">What we collect</h2>
          <p className="mt-2">
            When you create an account, we collect your name, work email, organization name, and
            the data you choose to add to your workspace. When you submit a demo request or
            contact form, we collect the details you provide in that form. We do not collect
            data from you through any other means.
          </p>
        </section>
        <section>
          <h2 className="text-base font-semibold text-[var(--fg-default)]">How we use it</h2>
          <p className="mt-2">
            Account data is used to operate your workspace, including tenant isolation, access
            control, and audit logging within the product. Demo request and contact form
            submissions are used to respond to your inquiry.
          </p>
        </section>
        <section>
          <h2 className="text-base font-semibold text-[var(--fg-default)]">Cookies</h2>
          <p className="mt-2">
            We use a single, strictly necessary session cookie to keep you signed in. We do not
            use advertising or tracking cookies, and no third-party analytics provider is
            integrated into this product today. See our{" "}
            <Link href="/cookies" className="underline hover:text-[var(--fg-default)]">
              Cookie Policy
            </Link>{" "}
            for details.
          </p>
        </section>
        <section>
          <h2 className="text-base font-semibold text-[var(--fg-default)]">Data sharing</h2>
          <p className="mt-2">
            We do not sell your data. Data is shared with third-party providers only when you
            choose to connect an integration (see our{" "}
            <Link href="/trust" className="underline hover:text-[var(--fg-default)]">
              Security &amp; Trust
            </Link>{" "}
            page), and only for the scope you authorize.
          </p>
        </section>
        <section>
          <h2 className="text-base font-semibold text-[var(--fg-default)]">Contact</h2>
          <p className="mt-2">
            Questions about this policy can be sent through our{" "}
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
