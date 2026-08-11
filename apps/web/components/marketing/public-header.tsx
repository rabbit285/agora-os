"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Menu, X } from "lucide-react";

import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { useCurrentUser } from "@/lib/session";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { label: "Product", href: "/features" },
  { label: "Solutions", href: "/solutions" },
  { label: "Security", href: "/trust" },
  { label: "Pricing", href: "/pricing" },
];

/** The public marketing nav bar. Height is constant
 * (`--header-height-marketing`); scroll only lifts it with a shadow and
 * border, which costs no layout. It adapts its CTA area to auth state — a
 * signed-in visitor sees "Go to dashboard" instead of "Sign in" / "Start
 * free", the same client-side pattern the rest of the app already uses for
 * permission-gated UI (useCurrentUser is the same hook AuthGuard relies
 * on). */
export function PublicHeader() {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { data: user } = useCurrentUser();

  useEffect(() => {
    function onScroll() {
      setScrolled(window.scrollY > 8);
    }
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!mobileOpen) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setMobileOpen(false);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen]);

  return (
    <header
      className={cn(
        "sticky top-0 z-40 border-b bg-[var(--nav-bg)]/95 backdrop-blur transition-[box-shadow,border-color] duration-[var(--transition-base)]",
        scrolled ? "border-[var(--nav-border)] shadow-lg shadow-black/20" : "border-transparent",
      )}
    >
      <div className="mx-auto flex h-[var(--header-height-marketing)] max-w-[var(--content-max-width)] items-center justify-between px-4 sm:px-6 lg:px-8">
        <Logo size="md" tone="nav" />

        <nav aria-label="Site" className="hidden items-center gap-1 lg:flex">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="rounded-[var(--radius-md)] px-3.5 py-2 text-sm font-medium text-[var(--nav-fg-muted)] transition-colors hover:bg-[var(--nav-hover)] hover:text-[var(--nav-fg)]"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="hidden items-center gap-2 lg:flex">
          {user ? (
            <Button asChild>
              <Link href="/dashboard">Go to dashboard</Link>
            </Button>
          ) : (
            <>
              <Button
                asChild
                variant="ghost"
                className="text-[var(--nav-fg-muted)] hover:bg-[var(--nav-hover)] hover:text-[var(--nav-fg)]"
              >
                <Link href="/login">Sign in</Link>
              </Button>
              <Button
                asChild
                variant="outline"
                className="border-[var(--nav-border)] bg-transparent text-[var(--nav-fg)] hover:bg-[var(--nav-hover)]"
              >
                <Link href="/contact">Request a demo</Link>
              </Button>
              <Button asChild>
                <Link href="/signup">Start free</Link>
              </Button>
            </>
          )}
        </div>

        <button
          type="button"
          className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-md)] text-[var(--nav-fg)] hover:bg-[var(--nav-hover)] lg:hidden"
          aria-label={mobileOpen ? "Close menu" : "Open menu"}
          aria-expanded={mobileOpen}
          aria-controls="public-mobile-menu"
          onClick={() => setMobileOpen((open) => !open)}
        >
          {mobileOpen ? <X className="h-5 w-5" aria-hidden="true" /> : <Menu className="h-5 w-5" aria-hidden="true" />}
        </button>
      </div>

      {mobileOpen && (
        <nav
          id="public-mobile-menu"
          aria-label="Mobile"
          className="border-t border-[var(--nav-border)] bg-[var(--nav-bg)] px-4 py-4 lg:hidden"
        >
          <ul className="flex flex-col gap-1">
            {NAV_LINKS.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  className="block rounded-[var(--radius-md)] px-3 py-3 text-base font-medium text-[var(--nav-fg)] hover:bg-[var(--nav-hover)]"
                  onClick={() => setMobileOpen(false)}
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex flex-col gap-2 border-t border-[var(--nav-border)] pt-4">
            {user ? (
              <Button asChild>
                <Link href="/dashboard">Go to dashboard</Link>
              </Button>
            ) : (
              <>
                <Button
                  asChild
                  variant="outline"
                  className="border-[var(--nav-border)] bg-transparent text-[var(--nav-fg)] hover:bg-[var(--nav-hover)]"
                >
                  <Link href="/login">Sign in</Link>
                </Button>
                <Button
                  asChild
                  variant="outline"
                  className="border-[var(--nav-border)] bg-transparent text-[var(--nav-fg)] hover:bg-[var(--nav-hover)]"
                >
                  <Link href="/contact">Request a demo</Link>
                </Button>
                <Button asChild>
                  <Link href="/signup">Start free</Link>
                </Button>
              </>
            )}
          </div>
        </nav>
      )}
    </header>
  );
}
