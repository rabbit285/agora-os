import Image from "next/image";
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

/** Desktop: the trust message on the left, the form on the right. Mobile:
 * form only — the side panel is `hidden lg:flex`, not just visually
 * de-emphasized, so small screens never pay its layout cost. The logo
 * above the form is a real link back to the homepage, not decoration.
 *
 * The swap is done with `order` rather than by reordering the markup: the
 * form stays first in the DOM, so it is still what a screen reader reaches
 * first and what the skip link lands on. Nothing in the side panel is
 * focusable, so there is no visual/focus order mismatch to worry about. */
export function AuthLayout({
  children,
  sideTitle = "One governed workspace for compliance, security, sales, and support.",
  sideDescription = "Every action stays permission-aware, reviewable, and auditable.",
}: AuthLayoutProps) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div
        id="main-content"
        className="flex flex-col items-center justify-center px-4 py-12 sm:px-6 lg:order-2"
      >
        <div className="mb-8">
          <Logo size="lg" />
        </div>
        {/* max-w-sm left the card at 384px marooned in a half-screen
            panel roughly 950px wide on a desktop display. Signing in is
            the only task on the page, so the form should own it. */}
        <div className="w-full max-w-md lg:max-w-lg">{children}</div>
      </div>

      <div className="relative hidden overflow-hidden bg-[var(--gray-900)] lg:order-1 lg:flex lg:flex-col lg:justify-center lg:px-16">
        <Image
          src="/images/auth-tower.jpg"
          // Decorative: the panel's message is carried entirely by the
          // heading and list beside it, so describing the photo would only
          // add noise for a screen reader.
          alt=""
          fill
          sizes="50vw"
          // Not `priority`: this panel is hidden below lg, and even on
          // desktop the form is the task — the photo should never compete
          // with it for bandwidth.
          className="object-cover"
        />
        {/* The photograph is bright (open sky, sun flare, white cloud) and
            the copy over it is white, so it needs a real scrim rather than
            a tint. Weighted toward the left, where the text sits, and
            eased off toward the right so the building stays legible. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-[linear-gradient(100deg,rgba(2,6,23,0.86)_0%,rgba(2,6,23,0.74)_45%,rgba(2,6,23,0.46)_100%)]"
        />
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
