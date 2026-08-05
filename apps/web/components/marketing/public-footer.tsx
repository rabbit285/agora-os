import Link from "next/link";

import { Logo } from "@/components/logo";

const FOOTER_COLUMNS: { title: string; links: { label: string; href: string }[] }[] = [
  {
    title: "Product",
    links: [
      { label: "Product", href: "/features" },
      { label: "Solutions", href: "/solutions" },
      { label: "Pricing", href: "/pricing" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "About", href: "/about" },
      { label: "Contact", href: "/contact" },
      { label: "Security", href: "/trust" },
    ],
  },
  {
    title: "Legal",
    links: [
      { label: "Privacy Policy", href: "/privacy" },
      { label: "Terms of Service", href: "/terms" },
      { label: "Cookie Policy", href: "/cookies" },
    ],
  },
];

/** No "Documentation" column — no public docs exist to link to (per the
 * brief's own "only when real resources exist" instruction). */
export function PublicFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="border-t border-[var(--border-default)] bg-[var(--bg-app)]">
      <div className="mx-auto max-w-[var(--content-max-width)] px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid grid-cols-2 gap-8 sm:grid-cols-4">
          <div className="col-span-2 sm:col-span-1">
            <Logo size="sm" />
            <p className="mt-3 max-w-xs text-xs leading-relaxed text-[var(--fg-muted)]">
              The secure AI operating system for European SMEs — compliance, security, sales,
              support, and automation in one governed workspace.
            </p>
          </div>
          {FOOTER_COLUMNS.map((column) => (
            <div key={column.title}>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--fg-subtle)]">
                {column.title}
              </h3>
              <ul className="mt-3 flex flex-col gap-2">
                {column.links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className="text-sm text-[var(--fg-muted)] hover:text-[var(--fg-default)]"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-10 flex flex-col gap-4 border-t border-[var(--border-default)] pt-6 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-[var(--fg-subtle)]">
            © {year} Agora Origin. All rights reserved.
          </p>
          <Link
            href="/login"
            className="text-xs font-medium text-[var(--fg-muted)] hover:text-[var(--fg-default)]"
          >
            Sign in
          </Link>
        </div>
      </div>
    </footer>
  );
}
