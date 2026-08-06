import { CheckCircle2 } from "lucide-react";

import { Logo } from "@/components/logo";

const VALUE_POINTS = [
  "Tenant-isolated, permission-aware by default",
  "Every action is reviewable and auditable",
  "Compliance, security, sales, and support — one workspace",
];

type AuthLayoutProps = {
  children: React.ReactNode;
  sideTitle?: string;
  sideDescription?: string;
};

/** Desktop: the form on one side, a trust message on the other, per the
 * brief's own requested layout. Mobile: form only — the side panel is
 * `hidden lg:flex`, not just visually de-emphasized, so small screens
 * never pay its layout cost. The logo above the form is a real link back
 * to the homepage, not decoration. */
export function AuthLayout({
  children,
  sideTitle = "One governed workspace for compliance, security, sales, and support.",
  sideDescription = "Every action stays permission-aware, reviewable, and auditable.",
}: AuthLayoutProps) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div id="main-content" className="flex flex-col items-center justify-center px-4 py-12 sm:px-6">
        <div className="mb-8">
          <Logo size="lg" />
        </div>
        <div className="w-full max-w-sm">{children}</div>
      </div>

      <div className="relative hidden overflow-hidden bg-[var(--gray-900)] lg:flex lg:flex-col lg:justify-center lg:px-16">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_50%_at_50%_0%,rgba(99,102,241,0.25),transparent)]"
        />
        <div className="relative max-w-md">
          <h2 className="text-2xl font-semibold leading-snug text-white">{sideTitle}</h2>
          <p className="mt-4 text-sm leading-relaxed text-[var(--gray-400)]">{sideDescription}</p>
          <ul className="mt-8 flex flex-col gap-3">
            {VALUE_POINTS.map((point) => (
              <li key={point} className="flex items-start gap-2.5 text-sm text-[var(--gray-300)]">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[var(--primary-500)]" aria-hidden="true" />
                {point}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
