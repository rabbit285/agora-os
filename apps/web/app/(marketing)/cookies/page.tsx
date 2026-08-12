import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Cookie Policy — Veyntra",
  description: "The cookies Veyntra uses, and the ones it doesn't.",
  alternates: { canonical: "/cookies" },
};

export default function CookiesPage() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-16 sm:px-6 lg:px-8">
      <h1 className="text-2xl font-semibold text-[var(--fg-default)]">Cookie Policy</h1>
      <p className="mt-2 text-xs text-[var(--fg-muted)]">Last updated: August 2026</p>

      <div className="mt-8 flex flex-col gap-6 text-sm leading-relaxed text-[var(--fg-muted)]">
        <section>
          <h2 className="text-base font-semibold text-[var(--fg-default)]">What we use</h2>
          <p className="mt-2">
            Veyntra sets exactly one cookie: a strictly necessary, HttpOnly session cookie
            used to keep you signed in. It cannot be read by JavaScript and is not used for
            tracking.
          </p>
        </section>
        <section>
          <h2 className="text-base font-semibold text-[var(--fg-default)]">What we don&apos;t use</h2>
          <p className="mt-2">
            We do not use advertising cookies, cross-site tracking cookies, or any third-party
            analytics cookies. No third-party analytics provider is integrated into this product
            today.
          </p>
        </section>
        <section>
          <h2 className="text-base font-semibold text-[var(--fg-default)]">Managing cookies</h2>
          <p className="mt-2">
            Because our only cookie is required to keep you signed in, blocking it will prevent
            you from staying logged in to your workspace. It does not affect your ability to
            browse our public pages.
          </p>
        </section>
      </div>
    </div>
  );
}
