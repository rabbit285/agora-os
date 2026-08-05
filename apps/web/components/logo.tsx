import Link from "next/link";

import { cn } from "@/lib/utils";

const SIZE_MAP = {
  sm: { mark: 20, text: "text-sm" },
  md: { mark: 26, text: "text-base" },
  lg: { mark: 34, text: "text-xl" },
} as const;

type LogoProps = {
  size?: keyof typeof SIZE_MAP;
  markOnly?: boolean;
  href?: string | null;
  className?: string;
};

/** A minimal geometric mark (a governed center — concentric nodes, not a
 * literal shield/lock cliché) plus the wordmark, replacing the plain text
 * string every prior surface (AppSidebar, the (auth) layout) rendered on
 * its own. href={null} renders a non-interactive span instead of a link,
 * for contexts (e.g. an auth card that shouldn't navigate away) where a
 * clickable logo would be the wrong affordance. */
export function Logo({ size = "md", markOnly = false, href = "/", className }: LogoProps) {
  const { mark, text } = SIZE_MAP[size];

  const content = (
    <span className={cn("inline-flex items-center gap-2", className)}>
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

export function LogoMark({ size = 26, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      className={className}
    >
      <rect width="32" height="32" rx="8" fill="var(--brand-primary)" />
      <circle cx="16" cy="16" r="8.5" stroke="white" strokeOpacity="0.9" strokeWidth="1.6" />
      <circle cx="16" cy="16" r="2.5" fill="white" />
      <circle cx="23" cy="16" r="1.6" fill="white" />
      <circle cx="9" cy="16" r="1.6" fill="white" />
      <circle cx="16" cy="9" r="1.6" fill="white" />
      <circle cx="16" cy="23" r="1.6" fill="white" />
    </svg>
  );
}
