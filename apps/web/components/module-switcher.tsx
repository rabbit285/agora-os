"use client";

import Link from "next/link";

import { MODULES } from "@/lib/navigation";

export function ModuleSwitcher() {
  return (
    <div className="flex items-center gap-1 overflow-x-auto">
      {MODULES.map((module) => (
        <Link
          key={module.key}
          href={module.implemented ? module.href : `/coming-soon?module=${module.key}`}
          className="whitespace-nowrap rounded-md px-3 py-1.5 text-sm text-neutral-600 hover:bg-neutral-100"
        >
          {module.label}
        </Link>
      ))}
    </div>
  );
}
