"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { apiFetch } from "@/lib/api";
import { useCurrentUser } from "@/lib/session";

/**
 * Client-side redirect gate. Authorization itself is enforced server-side
 * by the API on every request (docs/SECURITY_ARCHITECTURE.md) — this only
 * prevents rendering an empty/broken UI before redirecting an unauthenticated
 * visitor to /login.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { data: user, isLoading, isError } = useCurrentUser();

  useEffect(() => {
    if (isLoading || (!isError && user)) return;
    // Clear the cookie *before* redirecting. `middleware.ts` decides
    // "logged in" on cookie presence alone (a deliberate trade to keep a
    // database round-trip off every request), so redirecting to /login
    // while a dead cookie is still set gets bounced straight back here —
    // and this component renders null, leaving a blank page with no way
    // out. Logging out first is what makes the redirect land.
    let cancelled = false;
    void (async () => {
      try {
        await apiFetch("/api/v1/auth/logout", { method: "POST" });
      } catch {
        // Best effort: a failed logout must not strand the user on a
        // blank screen. Redirect regardless.
      }
      if (!cancelled) router.replace("/login");
    })();
    return () => {
      cancelled = true;
    };
  }, [isLoading, isError, user, router]);

  if (isLoading) {
    return (
      <div
        role="status"
        aria-label="Loading"
        className="flex h-screen items-center justify-center bg-[var(--bg-app)] text-sm text-[var(--fg-subtle)]"
      >
        Loading…
      </div>
    );
  }
  if (isError || !user) {
    return null;
  }
  return <>{children}</>;
}
