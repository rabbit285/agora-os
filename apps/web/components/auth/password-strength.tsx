import { cn } from "@/lib/utils";

/** The backend enforces exactly one real rule — 12 to 200 characters, no
 * complexity requirement (docs/AUTH_UX_AUDIT.md §3). This indicator only
 * ever reflects that real rule; it does not imply an uppercase/digit/
 * symbol requirement the server doesn't actually enforce. */
export function PasswordStrength({ password }: { password: string }) {
  const meetsLength = password.length >= 12;
  const level = password.length === 0 ? 0 : meetsLength ? (password.length >= 20 ? 2 : 1) : 0;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex gap-1">
        {[0, 1, 2].map((segment) => (
          <div
            key={segment}
            className={cn(
              "h-1 flex-1 rounded-full transition-colors duration-[var(--transition-fast)]",
              segment < level
                ? level === 1
                  ? "bg-[var(--warning-500)]"
                  : "bg-[var(--success-500)]"
                : "bg-[var(--gray-200)]",
            )}
          />
        ))}
      </div>
      <p className={cn("text-xs", meetsLength ? "text-[var(--success-600)]" : "text-[var(--fg-subtle)]")}>
        At least 12 characters {meetsLength ? "✓" : `(${password.length}/12)`}
      </p>
    </div>
  );
}
