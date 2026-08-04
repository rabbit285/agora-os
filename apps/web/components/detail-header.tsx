import { Breadcrumbs, type Breadcrumb } from "@/components/breadcrumbs";
import { cn } from "@/lib/utils";

/** Standardized entity detail-page header — title, status/health slot,
 * metadata row (owner, dates, whatever the page needs), primary actions.
 * Used in place of PageHeader on entity detail pages (AI systems, security
 * incidents, vendors, accounts, tickets, workflows, ...). */
export function DetailHeader({
  title,
  subtitle,
  status,
  metadata,
  actions,
  breadcrumbs,
  className,
}: {
  title: string;
  subtitle?: string;
  status?: React.ReactNode;
  metadata?: React.ReactNode;
  actions?: React.ReactNode;
  breadcrumbs?: Breadcrumb[];
  className?: string;
}) {
  return (
    <div className={cn("mb-6", className)}>
      {breadcrumbs && <Breadcrumbs items={breadcrumbs} />}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-semibold text-[var(--fg-default)]">{title}</h1>
            {status}
          </div>
          {subtitle && <p className="mt-1 text-xs text-[var(--fg-muted)]">{subtitle}</p>}
          {metadata && (
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--fg-muted)]">
              {metadata}
            </div>
          )}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
    </div>
  );
}
