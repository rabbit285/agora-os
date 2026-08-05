"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";

import { Dialog, DialogContent } from "@/components/ui/dialog";
import { NAVIGATION } from "@/lib/navigation";

type Destination = { label: string; href: string; group: string };

const DESTINATIONS: Destination[] = NAVIGATION.flatMap((group) =>
  group.items
    .filter((item) => item.implemented)
    .map((item) => ({ label: item.label, href: item.href, group: group.label })),
);

/** Global ⌘K / Ctrl+K navigation palette. */
export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) setQuery("");
  }

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return DESTINATIONS;
    return DESTINATIONS.filter(
      (d) => d.label.toLowerCase().includes(q) || d.group.toLowerCase().includes(q),
    );
  }, [query]);

  function go(href: string) {
    setOpen(false);
    router.push(href);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent hideClose className="top-[20%] max-w-md translate-y-0 p-0">
        <div className="flex items-center gap-2 border-b border-[var(--border-default)] px-3 py-2.5">
          <Search className="h-4 w-4 text-[var(--fg-subtle)]" aria-hidden="true" />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Jump to…"
            aria-label="Search destinations"
            className="w-full bg-transparent text-sm text-[var(--fg-default)] placeholder:text-[var(--fg-subtle)] focus:outline-none"
          />
          <kbd className="rounded-[var(--radius-sm)] border border-[var(--border-default)] px-1.5 py-0.5 text-[10px] text-[var(--fg-subtle)]">
            Esc
          </kbd>
        </div>
        <div className="max-h-80 overflow-y-auto p-1.5">
          {results.length === 0 && (
            <p className="px-2 py-4 text-center text-xs text-[var(--fg-subtle)]">No matches.</p>
          )}
          {results.map((destination) => (
            <button
              key={destination.href}
              type="button"
              onClick={() => go(destination.href)}
              className="flex w-full items-center justify-between rounded-[var(--radius-sm)] px-2.5 py-1.5 text-left text-sm text-[var(--fg-default)] hover:bg-[var(--bg-surface-hover)] focus-visible:bg-[var(--bg-surface-hover)] focus-visible:outline-none"
            >
              {destination.label}
              <span className="text-[11px] text-[var(--fg-subtle)]">{destination.group}</span>
            </button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
