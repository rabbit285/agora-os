"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { AuthCard } from "@/components/auth/auth-card";
import { AuthLayout } from "@/components/auth/auth-layout";
import { VerificationState } from "@/components/auth/verification-state";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import { useCurrentUser } from "@/lib/session";

type Status = "verifying" | "success" | "invalid-or-expired";

export function VerifyEmailStatus({ token }: { token: string }) {
  const [status, setStatus] = useState<Status>("verifying");
  const [resendState, setResendState] = useState<"idle" | "sending" | "sent">("idle");
  // Authenticated only if the visitor happens to be signed in (e.g. they
  // opened this link in the same browser they signed up in) — the resend
  // action requires it (docs/AUTH_UX_AUDIT.md §2), and a signed-in visitor
  // whose email is already verified can skip the token check entirely
  // (derived directly below, not via an effect-triggered state update).
  const { data: user, isLoading: userLoading } = useCurrentUser();
  const alreadyVerified = Boolean(user?.email_verified_at);

  useEffect(() => {
    if (userLoading || alreadyVerified) return;
    let cancelled = false;
    apiFetch("/api/v1/auth/verify-email", { method: "POST", body: { token } })
      .then(() => {
        if (!cancelled) setStatus("success");
      })
      .catch(() => {
        if (!cancelled) setStatus("invalid-or-expired");
      });
    return () => {
      cancelled = true;
    };
  }, [token, userLoading, alreadyVerified]);

  async function resend() {
    setResendState("sending");
    try {
      await apiFetch("/api/v1/auth/resend-verification-email", { method: "POST" });
      setResendState("sent");
    } catch {
      setResendState("idle");
    }
  }

  if (status === "verifying" && !alreadyVerified) {
    return (
      <AuthLayout>
        <AuthCard title="Email verification">
          <VerificationState status="pending" title="Verifying your email…" />
        </AuthCard>
      </AuthLayout>
    );
  }

  if (alreadyVerified || status === "success") {
    return (
      <AuthLayout>
        <AuthCard title="Email verification">
          <VerificationState
            status="success"
            title="Your email is verified"
            description="You're all set."
            action={
              <Button asChild className="mt-2">
                <Link href="/dashboard">Go to dashboard</Link>
              </Button>
            }
          />
        </AuthCard>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <AuthCard title="Email verification">
        <VerificationState
          status="error"
          title="This link no longer works"
          // Same undifferentiated signal the backend actually returns for
          // an invalid, already-used, and expired token
          // (docs/AUTH_UX_AUDIT.md §3) — not fabricating a distinction it
          // can't make.
          description="It may have already been used or its 48-hour window has passed."
          action={
            <div className="mt-2 flex flex-col items-center gap-2">
              {user ? (
                <Button
                  type="button"
                  variant="outline"
                  disabled={resendState !== "idle"}
                  onClick={resend}
                >
                  {resendState === "sending"
                    ? "Sending…"
                    : resendState === "sent"
                      ? "New link sent — check your email"
                      : "Send a new link"}
                </Button>
              ) : (
                <Button asChild variant="outline">
                  <Link href="/login">Sign in to request a new link</Link>
                </Button>
              )}
              <Link href="/login" className="text-sm text-[var(--fg-muted)] hover:underline">
                Back to sign in
              </Link>
            </div>
          }
        />
      </AuthCard>
    </AuthLayout>
  );
}
