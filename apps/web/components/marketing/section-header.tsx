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
        <p
          className={cn(
            "flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-[var(--fg-muted)]",
            align === "center" && "justify-center",
          )}
        >
          {/* A two-tone tick standing in for the mark's two arcs — enough
              brand presence to tie every section back to the logo without
              repeating the full mark down the page. */}
          <span
            aria-hidden="true"
            className="h-3 w-1 rounded-full bg-[image:var(--gradient-arc-teal)]"
          />
          {eyebrow}
        </p>
      )}
      <h2 className="mt-2 text-[length:var(--text-3xl)] font-semibold tracking-tight text-[var(--fg-default)]">
        {title}
      </h2>
      {description && (
        <p className="mt-3 text-base leading-relaxed text-[var(--fg-muted)]">{description}</p>
      )}
    </div>
  );
}
