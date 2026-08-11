import Link from "next/link";
import { ArrowRight, Sparkles } from "lucide-react";

import { LogoMark } from "@/components/logo";
import { cn } from "@/lib/utils";

/** The dashboard's opening panel — the app-side counterpart to the
 * marketing hero, carrying the same two-lobe brand wash so signing in
 * doesn't feel like arriving at a different product.
 *
 * The AI briefing lives inside it rather than in a separate card below:
 * the briefing is the one thing on this page that is genuinely *generated*
 * rather than counted, so it belongs next to the spark in the mark. When
 * there is no briefing the panel quietly collapses to a greeting instead
 * of showing an empty AI slot. */
export function DashboardHero({
  title,
  description,
  briefing,
  briefingHref,
  loading = false,
  className,
}: {
  title: string;
  description?: string;
  briefing?: string | null;
  briefingHref?: string;
  loading?: boolean;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "relative isolate overflow-hidden rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)]",
        className,
      )}
    >
      <div
        aria-hidden="true"
        className="brand-aurora-panel pointer-events-none absolute inset-0"
      />
      {/* The full brand sweep as a top rule — the app's one recurring
          signature, matching the hairline that closes the marketing hero. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-[image:var(--gradient-brand)]"
      />

      <div className="relative flex flex-col gap-5 p-5 sm:p-6">
        <div className="flex items-start gap-4">
          <LogoMark size={36} className="mt-0.5 shrink-0" idSuffix="dashboard-hero" />
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight text-[var(--fg-default)]">
              {title}
            </h1>
            {description && (
              <p className="mt-1 text-xs leading-relaxed text-[var(--fg-muted)]">{description}</p>
            )}
          </div>
        </div>

        {loading ? (
          <div className="rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)]/70 p-4">
            <div className="h-3 w-32 animate-pulse rounded bg-[var(--bg-sunken)]" />
            <div className="mt-2.5 h-3 w-full animate-pulse rounded bg-[var(--bg-sunken)]" />
            <div className="mt-1.5 h-3 w-4/5 animate-pulse rounded bg-[var(--bg-sunken)]" />
          </div>
        ) : briefing ? (
          <div className="rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)]/80 p-4 backdrop-blur-sm">
            <p className="flex items-center gap-1.5 text-xs font-semibold text-[var(--fg-default)]">
              <Sparkles className="h-3.5 w-3.5 text-[var(--brand-spark)]" aria-hidden="true" />
              Today&rsquo;s AI briefing
            </p>
            <p className="mt-2 text-sm leading-relaxed text-[var(--fg-muted)]">{briefing}</p>
            {briefingHref && (
              <Link
                href={briefingHref}
                className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-[var(--brand-primary)] hover:underline"
              >
                View full daily briefing
                <ArrowRight className="h-3 w-3" aria-hidden="true" />
              </Link>
            )}
          </div>
        ) : null}
      </div>
    </section>
  );
}
