import { cn } from "@/lib/utils";

type SectionHeaderProps = {
  eyebrow?: string;
  title: string;
  description?: string;
  align?: "left" | "center";
  className?: string;
};

export function SectionHeader({ eyebrow, title, description, align = "center", className }: SectionHeaderProps) {
  return (
    <div className={cn("max-w-2xl", align === "center" && "mx-auto text-center", className)}>
      {eyebrow && (
        <p className="text-xs font-semibold uppercase tracking-wide text-[var(--brand-primary)]">
          {eyebrow}
        </p>
      )}
      <h2 className="mt-2 text-[var(--text-3xl)] font-semibold tracking-tight text-[var(--fg-default)]">
        {title}
      </h2>
      {description && (
        <p className="mt-3 text-base leading-relaxed text-[var(--fg-muted)]">{description}</p>
      )}
    </div>
  );
}
