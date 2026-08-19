import Link from "next/link";

/** Shown for any route the product does not have — including the sales,
 * support and automation screens Veyntra retired when it narrowed to
 * compliance. Deliberately does not offer to "take you to the old page":
 * those modules are gone from the product, and pretending otherwise is
 * how a stale bookmark turns into a support ticket. */
export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-[var(--bg-app)] px-6 text-center">
      <p className="mb-2 text-sm font-medium uppercase tracking-wide text-[var(--fg-subtle)]">
        404
      </p>
      <h1 className="mb-3 text-2xl font-semibold text-[var(--fg-default)]">
        This page isn&apos;t part of Veyntra
      </h1>
      <p className="mb-6 max-w-md text-sm leading-relaxed text-[var(--fg-muted)]">
        Veyntra is a compliance platform. If you followed an old link to a sales, support or
        automation screen, those are no longer part of the product.
      </p>
      <Link
        href="/compliance"
        className="rounded-[var(--radius-md)] bg-[var(--brand-primary)] px-4 py-2 text-sm font-medium text-white"
      >
        Go to Compliance
      </Link>
    </main>
  );
}
