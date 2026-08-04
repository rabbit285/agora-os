"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";

type Status = "verifying" | "success" | "error";

export function VerifyEmailStatus({ token }: { token: string }) {
  const [status, setStatus] = useState<Status>("verifying");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch("/api/v1/auth/verify-email", { method: "POST", body: { token } })
      .then(() => {
        if (!cancelled) setStatus("success");
      })
      .catch((error) => {
        if (cancelled) return;
        setErrorMessage(error instanceof ApiError ? error.message : "Something went wrong");
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Email verification</CardTitle>
      </CardHeader>
      <CardContent>
        {status === "verifying" && <p className="text-sm text-[var(--fg-muted)]">Verifying your email…</p>}
        {status === "success" && (
          <p className="text-sm text-[var(--fg-default)]">
            Your email address has been verified. You&apos;re all set.
          </p>
        )}
        {status === "error" && (
          <p className="text-sm text-[var(--critical-600)]">{errorMessage ?? "This link is invalid or expired."}</p>
        )}
        <div className="mt-4 text-center">
          <Button asChild>
            <Link href="/">Go to dashboard</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
