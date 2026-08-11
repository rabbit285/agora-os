"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { MODULES } from "@/lib/navigation";
import { cn } from "@/lib/utils";

export function ModuleSwitcher() {
  const pathname = usePathname();

  return (
    <div className="flex items-center gap-1 overflow-x-auto">
      {MODULES.map((module) => {
        const active = pathname.startsWith(module.href);
        return (
          <Link
            key={module.key}
            href={module.implemented ? module.href : `/coming-soon?module=${module.key}`}
            className={cn(
              "whitespace-nowrap rounded-[var(--radius-md)] px-3 py-1.5 text-sm transition-colors duration-[var(--transition-fast)]",
              active
                ? "bg-[var(--nav-active)] font-medium text-[var(--nav-fg)]"
                : "text-[var(--nav-fg-muted)] hover:bg-[var(--nav-hover)] hover:text-[var(--nav-fg)]",
            )}
          >
            {module.label}
          </Link>
        );
      })}
    </div>
  );
}
