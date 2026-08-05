import type { LucideIcon } from "lucide-react";

export type FeatureItem = {
  icon: LucideIcon;
  title: string;
  description: string;
};

/** Generic feature-bullet grid — reused by the /features page's per-module
 * detail sections. Deliberately plain (icon + title + description, no
 * card chrome) so it reads as documentation-grade content, not another
 * layer of decorative cards stacked on top of ModuleOverview's. */
export function FeatureGrid({ items, columns = 3 }: { items: FeatureItem[]; columns?: 2 | 3 }) {
  return (
    <div
      className={
        columns === 2
          ? "grid gap-6 sm:grid-cols-2"
          : "grid gap-6 sm:grid-cols-2 lg:grid-cols-3"
      }
    >
      {items.map((item) => (
        <div key={item.title} className="flex gap-3">
          <item.icon className="mt-0.5 h-5 w-5 shrink-0 text-[var(--brand-primary)]" aria-hidden="true" />
          <div>
            <h3 className="text-sm font-semibold text-[var(--fg-default)]">{item.title}</h3>
            <p className="mt-1 text-sm leading-relaxed text-[var(--fg-muted)]">{item.description}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
