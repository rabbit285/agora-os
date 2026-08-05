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

/** The public marketing nav bar. Becomes slightly more compact/elevated on
 * scroll (a subtle shadow + tighter height, not a layout jump) and adapts
 * its CTA area to auth state — a signed-in visitor sees "Go to dashboard"
 * instead of "Sign in" / "Start free", the same client-side pattern the
 * rest of the app already uses for permission-gated UI (useCurrentUser is
 * the same hook AuthGuard relies on). */
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
        "sticky top-0 z-40 border-b bg-[var(--bg-surface)]/95 backdrop-blur transition-[padding,box-shadow] duration-[var(--transition-base)]",
        scrolled
          ? "border-[var(--border-default)] shadow-[var(--shadow-token-sm)]"
          : "border-transparent",
      )}
    >
      <div
        className={cn(
          "mx-auto flex max-w-[var(--content-max-width)] items-center justify-between px-4 transition-[height] duration-[var(--transition-base)] sm:px-6 lg:px-8",
          scrolled ? "h-14" : "h-[var(--header-height)]",
        )}
      >
        <Logo size="md" />

        <nav aria-label="Product" className="hidden items-center gap-1 md:flex">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="rounded-[var(--radius-sm)] px-3 py-2 text-sm font-medium text-[var(--fg-muted)] transition-colors hover:bg-[var(--bg-surface-hover)] hover:text-[var(--fg-default)]"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="hidden items-center gap-2 md:flex">
          {user ? (
            <Button asChild size="sm">
              <Link href="/dashboard">Go to dashboard</Link>
            </Button>
          ) : (
            <>
              <Button asChild variant="ghost" size="sm">
                <Link href="/login">Sign in</Link>
              </Button>
              <Button asChild variant="outline" size="sm">
                <Link href="/contact">Request a demo</Link>
              </Button>
              <Button asChild size="sm">
                <Link href="/signup">Start free</Link>
              </Button>
            </>
          )}
        </div>

        <button
          type="button"
          className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-sm)] text-[var(--fg-default)] md:hidden"
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
          className="border-t border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-4 md:hidden"
        >
          <ul className="flex flex-col gap-1">
            {NAV_LINKS.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  className="block rounded-[var(--radius-sm)] px-3 py-2.5 text-sm font-medium text-[var(--fg-default)] hover:bg-[var(--bg-surface-hover)]"
                  onClick={() => setMobileOpen(false)}
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex flex-col gap-2 border-t border-[var(--border-default)] pt-4">
            {user ? (
              <Button asChild>
                <Link href="/dashboard">Go to dashboard</Link>
              </Button>
            ) : (
              <>
                <Button asChild variant="outline">
                  <Link href="/login">Sign in</Link>
                </Button>
                <Button asChild variant="outline">
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
