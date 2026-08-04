"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

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
    if (!isLoading && (isError || !user)) {
      router.replace("/login");
    }
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
