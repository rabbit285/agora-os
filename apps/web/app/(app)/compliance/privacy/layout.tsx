"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { apiFetch } from "@/lib/api";
import type { PrivacyOverview } from "@/lib/types";

/** The privacy workspace.
 *
 * This used to be one page with four lists stacked vertically, each with
 * its own form. That works at three records and fails at fifty: the
 * question a privacy officer opens the product with is not "show me
 * every processing activity", it is "what needs me this week" — and the
 * answer was buried under four headings nobody could scroll past.
 *
 * So the four record types get their own routes and the workspace opens
 * on the worklist. Tabs rather than four sidebar entries, because they
 * are four views of one job rather than four unrelated modules.
 */
const TABS = [
  { href: "/compliance/privacy", label: "Overview" },
  {
    href: "/compliance/privacy/processing-activities",
    label: "Processing activities",
  },
  { href: "/compliance/privacy/dpias", label: "DPIAs" },
  { href: "/compliance/privacy/data-requests", label: "Data requests" },
  { href: "/compliance/privacy/transfers", label: "Transfers" },
];

export default function PrivacyLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  // The count rides on the tab bar so the thing needing a person is
  // visible from every view, not only from the one that lists it.
  const { data: overview } = useQuery<PrivacyOverview>({
    queryKey: ["compliance", "privacy", "overview"],
    queryFn: () =>
      apiFetch<PrivacyOverview>("/api/v1/compliance/privacy/overview"),
    // Same reason as the suggestion counts: work arrives from document
    // analysis after the page has loaded, and a badge that never updates
    // is worse than no badge.
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
  });

  return (
    <div>
      <PageHeader
        title="Privacy"
        description="What personal data you process, the assessments that gate it, the requests people make about their own data, and where that data goes."
      />

      <nav
        aria-label="Privacy workspace"
        className="mb-5 flex flex-wrap gap-1 border-b border-[var(--border-default)]"
      >
        {TABS.map((tab) => {
          // Exact for Overview; prefix for the rest, so a record detail
          // route keeps its list tab lit.
          const active =
            tab.href === "/compliance/privacy"
              ? pathname === tab.href
              : pathname.startsWith(tab.href);
          const attention =
            tab.href === "/compliance/privacy" && overview?.needs_attention
              ? overview.needs_attention
              : 0;
          return (
            <Link
              key={tab.href}
              href={tab.href}
              aria-current={active ? "page" : undefined}
              className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
                active
                  ? "border-[var(--accent-600)] text-[var(--fg-default)]"
                  : "border-transparent text-[var(--fg-muted)] hover:text-[var(--fg-default)]"
              }`}
            >
              {tab.label}
              {attention > 0 && (
                <span className="ml-2 rounded-full bg-[var(--warning-100)] px-1.5 py-0.5 text-xs font-semibold text-[var(--warning-800)]">
                  {attention}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {children}
    </div>
  );
}
