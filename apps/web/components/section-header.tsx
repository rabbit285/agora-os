import type { ReactNode } from "react";

/** A section title with optional actions and a one-line explanation.
 *
 * Every section on the old stacked compliance page rolled its own
 * heading markup, which is how they drifted into six different sizes and
 * three different capitalisations. One component, one shape. */
export function SectionHeader({
  title,
  description,
  action,
  id,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  id?: string;
}) {
  return (
    // `scroll-mt` keeps the heading clear of the sticky top bar when a
    // link targets it by anchor.
    <div id={id} className="mb-3 scroll-mt-24">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          {title}
        </h2>
        {action}
      </div>
      {description && (
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-[var(--fg-muted)]">
          {description}
        </p>
      )}
    </div>
  );
}
