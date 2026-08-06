import Link from "next/link";
import type { AnchorHTMLAttributes, ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import { ArrowRight } from "lucide-react";

import { cn } from "@/lib/utils";

/** Shared hover/focus/press/selected motion classes for every interactive
 * card on the public site (module carousel slides, module-overview cards,
 * and any future card with a real destination). Deliberately NOT applied
 * to apps/web/components/ui/card.tsx itself — that component is shared by
 * 60+ authenticated dashboard/module pages and the auth card, none of
 * which should gain this hover treatment (see docs/PUBLIC_SITE_DESIGN.md
 * §12). Built as a standalone primitive instead. */
const INTERACTIVE_CARD_BASE =
  "group relative rounded-[var(--radius-lg)] border bg-[var(--bg-surface)] transition-[transform,opacity,box-shadow,border-color] duration-[var(--transition-card)] ease-[var(--ease-card)]";

const INTERACTIVE_CARD_HOVER =
  "hover:-translate-y-1 hover:scale-[1.02] hover:border-[var(--brand-primary)] hover:shadow-[var(--shadow-token-glow)] " +
  "focus-visible:-translate-y-1 focus-visible:scale-[1.02] focus-visible:border-[var(--brand-primary)] focus-visible:shadow-[var(--shadow-token-glow)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-app)] " +
  "active:translate-y-0 active:scale-[0.99] active:shadow-[var(--shadow-token-sm)] " +
  "motion-reduce:hover:translate-y-0 motion-reduce:hover:scale-100 motion-reduce:focus-visible:translate-y-0 motion-reduce:focus-visible:scale-100 motion-reduce:active:scale-100";

/** For cards with no click action of their own (e.g. a pricing card whose
 * real CTA is a nested Button) — a visual-only lift driven by :hover on
 * the card and :focus-within when the nested control gains focus, with no
 * cursor/role/tabIndex implying the card itself is clickable. */
const INTERACTIVE_CARD_PASSIVE_HOVER =
  "hover:border-[var(--brand-primary)] hover:shadow-[var(--shadow-token-glow)] focus-within:border-[var(--brand-primary)] focus-within:shadow-[var(--shadow-token-glow)]";

const INTERACTIVE_CARD_SELECTED = "border-[var(--brand-primary)] shadow-[var(--shadow-token-glow)]";
const INTERACTIVE_CARD_DEFAULT = "border-[var(--border-default)] shadow-[var(--shadow-token-sm)]";
const INTERACTIVE_CARD_DISABLED = "opacity-60 cursor-not-allowed";

type SharedProps = {
  /** Persistent "this is the current selection" state (e.g. the active
   * carousel slide) — visually identical to the hover state, but applied
   * unconditionally rather than only on :hover/:focus-visible. */
  selected?: boolean;
  disabled?: boolean;
  className?: string;
  children: ReactNode;
};

type LinkCardProps = SharedProps &
  Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "className" | "children" | "href"> & { href: string; onClick?: never };
type ButtonCardProps = SharedProps &
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className" | "children" | "onClick"> & {
    href?: undefined;
    onClick: () => void;
  };
type StaticCardProps = SharedProps &
  Omit<HTMLAttributes<HTMLDivElement>, "className" | "children"> & { href?: undefined; onClick?: undefined };

export type InteractiveCardProps = LinkCardProps | ButtonCardProps | StaticCardProps;

/** A card that is a real `<a>` (has `href`), a real `<button>` (has
 * `onClick`), or a plain, non-interactive `<div>` that still gets a
 * hover/focus-within visual lift for cards whose actual click target is a
 * nested control (see INTERACTIVE_CARD_PASSIVE_HOVER above) — never a
 * clickable `<div>` pretending to be a link or button. */
export function InteractiveCard({ selected, disabled, className, children, ...props }: InteractiveCardProps) {
  const classes = cn(
    INTERACTIVE_CARD_BASE,
    selected ? INTERACTIVE_CARD_SELECTED : INTERACTIVE_CARD_DEFAULT,
    disabled && INTERACTIVE_CARD_DISABLED,
    !disabled && ("href" in props || "onClick" in props) && INTERACTIVE_CARD_HOVER,
    !disabled && !("href" in props) && !("onClick" in props) && INTERACTIVE_CARD_PASSIVE_HOVER,
    className,
  );

  if (disabled) {
    return (
      <div className={classes} aria-disabled="true">
        {children}
      </div>
    );
  }

  if ("href" in props && props.href) {
    const { href, ...rest } = props as LinkCardProps;
    return (
      <Link href={href} className={classes} {...rest}>
        {children}
      </Link>
    );
  }

  if ("onClick" in props && props.onClick) {
    const { onClick, ...rest } = props as ButtonCardProps;
    return (
      <button type="button" onClick={onClick} className={classes} {...rest}>
        {children}
      </button>
    );
  }

  return <div className={classes}>{children}</div>;
}

/** Wraps a `next/image` (or any media) inside an interactive card so it
 * zooms subtly on the card's hover/focus — driven by the ancestor
 * InteractiveCard's own `group` class, no extra JS or re-render. The
 * image's own transition runs slightly slower than the card's
 * (--transition-card-media vs --transition-card) for a layered depth
 * feel, per docs/PUBLIC_SITE_DESIGN.md §12. */
export function CardMedia({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("relative overflow-hidden", className)}>
      <div className="absolute inset-0 transition-transform duration-[var(--transition-card-media)] ease-[var(--ease-card)] group-hover:scale-[1.05] group-focus-visible:scale-[1.05] motion-reduce:group-hover:scale-100 motion-reduce:group-focus-visible:scale-100">
        {children}
      </div>
    </div>
  );
}

/** A trailing arrow that nudges forward on the parent card's hover/focus —
 * the same affordance every "Explore <Module>" CTA already used inline;
 * centralized here so it's one definition, not six copies. */
export function CardActionArrow({ className }: { className?: string }) {
  return (
    <ArrowRight
      className={cn(
        "h-4 w-4 shrink-0 transition-transform duration-[var(--transition-card)] ease-[var(--ease-card)] group-hover:translate-x-1 group-focus-visible:translate-x-1 motion-reduce:group-hover:translate-x-0 motion-reduce:group-focus-visible:translate-x-0",
        className,
      )}
      aria-hidden="true"
    />
  );
}
