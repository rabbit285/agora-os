import Link from "next/link";
import { ChevronRight } from "lucide-react";

export type Breadcrumb = { label: string; href?: string };

export function Breadcrumbs({ items }: { items: Breadcrumb[] }) {
  if (items.length === 0) return null;
  return (
    <nav aria-label="Breadcrumb" className="mb-2 flex items-center gap-1.5 text-xs text-[var(--fg-muted)]">
      {items.map((item, index) => {
        const isLast = index === items.length - 1;
        return (
          <span key={`${item.label}-${index}`} className="flex items-center gap-1.5">
            {index > 0 && <ChevronRight className="h-3 w-3 text-[var(--fg-subtle)]" aria-hidden="true" />}
            {item.href && !isLast ? (
              <Link href={item.href} className="hover:text-[var(--fg-default)] hover:underline">
                {item.label}
              </Link>
            ) : (
              <span className={isLast ? "font-medium text-[var(--fg-default)]" : undefined}>
                {item.label}
              </span>
            )}
          </span>
        );
      })}
    </nav>
  );
}
