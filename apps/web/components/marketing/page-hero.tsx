import { cn } from "@/lib/utils";

/** The opening band for a marketing subpage.
 *
 * Every one of these pages previously began with a bare centred heading on
 * flat white, so a visitor arriving from the homepage's aurora hero hit an
 * abrupt drop in production value. This gives them the homepage's own
 * light and type scale, so the site reads as one design rather than a
 * landing page followed by documentation.
 *
 * `accent` is the tail of the title, painted with the brand text gradient.
 * It is a separate prop rather than embedded markup so callers can't
 * accidentally pass the decorative gradient, which is unreadable as text
 * (see --gradient-brand-text in app/globals.css).
 */
export function PageHero({
  eyebrow,
  title,
  accent,
  description,
  children,
  className,
}: {
  eyebrow: string;
  title: string;
  accent?: string;
  description?: string;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("relative isolate overflow-hidden bg-[var(--bg-app)]", className)}>
      <div
        aria-hidden="true"
        className="brand-aurora pointer-events-none absolute inset-x-0 -top-32 h-[34rem]"
      />
      <div className="relative mx-auto max-w-[var(--content-max-width)] px-4 py-20 text-center sm:px-6 lg:px-8 lg:py-24">
        <p className="flex items-center justify-center gap-2 text-xs font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          <span
            aria-hidden="true"
            className="h-3 w-1 rounded-full bg-[image:var(--gradient-arc-teal)]"
          />
          {eyebrow}
        </p>
        <h1 className="mx-auto mt-5 max-w-3xl text-[length:var(--text-display-2)] font-semibold leading-[1.08] tracking-tight text-[var(--fg-default)]">
          {title}
          {accent && (
            <>
              {" "}
              <span className="brand-gradient-text">{accent}</span>
            </>
          )}
        </h1>
        {description && (
          <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-[var(--fg-muted)]">
            {description}
          </p>
        )}
        {children && <div className="mt-9">{children}</div>}
      </div>
    </section>
  );
}
