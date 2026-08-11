import Link from "next/link";

import { cn } from "@/lib/utils";

const SIZE_MAP = {
  sm: { mark: 28, text: "text-base" },
  md: { mark: 46, text: "text-2xl" },
  lg: { mark: 52, text: "text-2xl" },
} as const;

type LogoProps = {
  size?: keyof typeof SIZE_MAP;
  markOnly?: boolean;
  href?: string | null;
  /** "nav" for the dark chrome (header, sidebar), which stays dark in both
   * themes — the default wordmark color would be near-invisible there. */
  tone?: "default" | "nav";
  className?: string;
};

/** The Agora Origin mark plus wordmark. href={null} renders a
 * non-interactive span instead of a link, for contexts (e.g. an auth card
 * that shouldn't navigate away) where a clickable logo would be the wrong
 * affordance. */
export function Logo({
  size = "md",
  markOnly = false,
  href = "/",
  tone = "default",
  className,
}: LogoProps) {
  const { mark, text } = SIZE_MAP[size];

  const content = (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark size={mark} />
      {!markOnly && (
        <span
          className={cn(
            "font-semibold tracking-tight",
            tone === "nav" ? "text-[var(--nav-fg)]" : "text-[var(--fg-default)]",
            text,
          )}
        >
          Agora Origin
        </span>
      )}
    </span>
  );

  if (href === null) {
    return content;
  }

  return (
    <Link href={href} className="inline-flex items-center" aria-label="Agora Origin home">
      {content}
    </Link>
  );
}

/** Two interlocking crescents around a warm spark.
 *
 * Each crescent is a filled path — outer arc, a straight chord across the
 * end, inner arc back, close — rather than a stroked circle segment. The
 * chord is what produces the angular cut on one tip, and running the inner
 * arc slightly shorter than the outer one tapers the other tip to a point.
 * A stroke with round caps can't do either; it gives two blunt ends and
 * reads as a pair of plain rings.
 *
 * The blue crescent is drawn first so the teal tip sits above it where they
 * cross, matching the mark's own overlap.
 *
 * Gradient ids are suffixed per instance — two marks on one page (header
 * and footer) would otherwise share one `<defs>` id, and the second would
 * silently inherit the first's gradient.
 */
export function LogoMark({
  size = 28,
  className,
  idSuffix = "default",
}: {
  size?: number;
  className?: string;
  idSuffix?: string;
}) {
  const tealId = `ao-arc-teal-${idSuffix}`;
  const blueId = `ao-arc-blue-${idSuffix}`;
  const sparkId = `ao-spark-${idSuffix}`;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      className={className}
    >
      <defs>
        <linearGradient id={tealId} x1="8" y1="12" x2="30" y2="38" gradientUnits="userSpaceOnUse">
          <stop stopColor="var(--brand-teal)" />
          <stop offset="1" stopColor="var(--brand-teal-bright)" />
        </linearGradient>
        <linearGradient id={blueId} x1="40" y1="12" x2="18" y2="38" gradientUnits="userSpaceOnUse">
          <stop stopColor="var(--brand-violet)" />
          <stop offset="1" stopColor="var(--brand-blue-deep)" />
        </linearGradient>
        <radialGradient id={sparkId} cx="0.5" cy="0.5" r="0.5">
          <stop stopColor="var(--brand-spark-soft)" stopOpacity="0.7" />
          <stop offset="1" stopColor="var(--brand-spark)" stopOpacity="0" />
        </radialGradient>
      </defs>

      <path
        d="M25.24 38A15.1 15.1 0 1 0 21.6 12.1L23.39 17.7A9.8 9.8 0 1 1 25.42 32.12Z"
        fill={`url(#${blueId})`}
      />
      <path
        d="M22.76 10A15.1 15.1 0 1 0 26.4 35.9L24.61 30.3A9.8 9.8 0 1 1 22.58 15.88Z"
        fill={`url(#${tealId})`}
      />

      {/* The spark's halo, then the four-point star itself. */}
      <circle cx="24" cy="24" r="7" fill={`url(#${sparkId})`} />
      <path
        d="M24 18.4c.42 3.2 2.18 4.96 5.38 5.38-3.2.42-4.96 2.18-5.38 5.38-.42-3.2-2.18-4.96-5.38-5.38 3.2-.42 4.96-2.18 5.38-5.38Z"
        fill="var(--brand-spark)"
      />
    </svg>
  );
}
