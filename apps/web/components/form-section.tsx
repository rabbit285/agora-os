import { cn } from "@/lib/utils";

/** Grouped-fields section with a heading — the one form layout pattern for
 * every create/edit form in the app, whether it sits in a page, a dialog,
 * or a drawer. */
export function FormSection({
  title,
  description,
  children,
  className,
}: {
  title?: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {title && (
        <div>
          <h3 className="text-sm font-semibold text-[var(--fg-default)]">{title}</h3>
          {description && <p className="mt-0.5 text-xs text-[var(--fg-muted)]">{description}</p>}
        </div>
      )}
      <div className="flex flex-col gap-3">{children}</div>
    </div>
  );
}

export function RequiredMark() {
  return (
    <span className="ml-0.5 text-[var(--critical-600)]" aria-hidden="true">
      *
    </span>
  );
}

export function FormHelperText({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-[var(--fg-subtle)]">{children}</p>;
}

export function FormErrorText({ children }: { children: React.ReactNode }) {
  return (
    <p role="alert" className="text-xs text-[var(--critical-600)]">
      {children}
    </p>
  );
}
