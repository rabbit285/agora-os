import Link from "next/link";

import { cn } from "@/lib/utils";

const SIZE_MAP = {
  sm: { mark: 22, text: "text-sm" },
  md: { mark: 28, text: "text-base" },
  lg: { mark: 38, text: "text-xl" },
} as const;

type LogoProps = {
  size?: keyof typeof SIZE_MAP;
  markOnly?: boolean;
  href?: string | null;
  className?: string;
};

/** The Agora Origin mark plus wordmark. href={null} renders a
 * non-interactive span instead of a link, for contexts (e.g. an auth card
 * that shouldn't navigate away) where a clickable logo would be the wrong
 * affordance. */
export function Logo({ size = "md", markOnly = false, href = "/", className }: LogoProps) {
  const { mark, text } = SIZE_MAP[size];

  const content = (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark size={mark} />
      {!markOnly && (
        <span className={cn("font-semibold tracking-tight text-[var(--fg-default)]", text)}>
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

/** Two interlocking arcs around a warm spark.
 *
 * The arcs are stroked circle segments with round caps rather than filled
 * outline paths: the shape is genuinely two sweeps of a circle, so
 * describing it that way keeps it crisp at every size (a 20px sidebar mark
 * and a 200px hero mark come off the same geometry) and lets the stroke
 * width scale proportionally instead of being baked into fill outlines.
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
        <linearGradient id={tealId} x1="6" y1="10" x2="30" y2="38" gradientUnits="userSpaceOnUse">
          <stop stopColor="var(--brand-teal)" />
          <stop offset="1" stopColor="var(--brand-cyan)" />
        </linearGradient>
        <linearGradient id={blueId} x1="42" y1="10" x2="20" y2="40" gradientUnits="userSpaceOnUse">
          <stop stopColor="var(--brand-violet)" />
          <stop offset="1" stopColor="var(--brand-blue-deep)" />
        </linearGradient>
        <radialGradient id={sparkId} cx="0.5" cy="0.5" r="0.5">
          <stop stopColor="var(--brand-spark-soft)" stopOpacity="0.55" />
          <stop offset="1" stopColor="var(--brand-spark)" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Two 256° sweeps of circles offset horizontally by ~0.96r, with
          their gaps rotated 15° off the horizontal. That rotation is what
          makes the mark read as one continuous loop: it lets each arc's
          tip pass *beside* the other's rather than colliding with it head
          on at the centerline, which is what produces the S through the
          middle. */}
      <path
        d="M27.83 31.22A12 12 0 1 1 22.94 12.95"
        stroke={`url(#${tealId})`}
        strokeWidth="5.8"
        strokeLinecap="round"
      />
      <path
        d="M20.17 16.78A12 12 0 1 1 25.06 35.05"
        stroke={`url(#${blueId})`}
        strokeWidth="5.8"
        strokeLinecap="round"
      />

      {/* The spark's halo, then the four-point star itself. */}
      <circle cx="24" cy="24" r="8.5" fill={`url(#${sparkId})`} />
      <path
        d="M24 16.6c.53 4.05 2.8 6.36 6.85 7.4-4.05 1.04-6.32 3.35-6.85 7.4-.53-4.05-2.8-6.36-6.85-7.4 4.05-1.04 6.32-3.35 6.85-7.4Z"
        fill="var(--brand-spark)"
      />
    </svg>
  );
}
