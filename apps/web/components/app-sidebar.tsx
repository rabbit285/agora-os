"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { NAVIGATION } from "@/lib/navigation";
import { cn } from "@/lib/utils";

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <nav className="flex w-60 shrink-0 flex-col gap-6 border-r border-neutral-200 bg-white p-4">
      <div className="px-2 text-lg font-semibold text-neutral-900">Agora Origin</div>
      {NAVIGATION.map((group) => (
        <div key={group.label} className="flex flex-col gap-1">
          <div className="px-2 text-xs font-semibold uppercase tracking-wide text-neutral-400">
            {group.label}
          </div>
          {group.items.map((item) => {
            const href = item.implemented
              ? item.href
              : `/coming-soon?module=${encodeURIComponent(item.label.toLowerCase())}`;
            const active = item.implemented && pathname === item.href;
            return (
              <Link
                key={item.href}
                href={href}
                className={cn(
                  "rounded-md px-2 py-1.5 text-sm transition-colors",
                  active
                    ? "bg-neutral-900 text-white"
                    : "text-neutral-700 hover:bg-neutral-100",
                  !item.implemented && "text-neutral-400",
                )}
              >
                {item.label}
                {!item.implemented && (
                  <span className="ml-2 text-[10px] uppercase text-neutral-400">soon</span>
                )}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
