"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AuthAlert } from "@/components/auth/auth-alert";
import { AuthCard } from "@/components/auth/auth-card";
import { AuthField } from "@/components/auth/auth-field";
import { AuthLayout } from "@/components/auth/auth-layout";
import { Button } from "@/components/ui/button";
import { ApiError, apiFetch } from "@/lib/api";

const schema = z.object({ email: z.string().email("Enter a valid email address") });
type FormValues = z.infer<typeof schema>;

const RESEND_COOLDOWN_SECONDS = 30;

export function ForgotPasswordClient() {
  const [submittedEmail, setSubmittedEmail] = useState<string | null>(null);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [rateLimited, setRateLimited] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setInterval(() => setResendCooldown((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(timer);
  }, [resendCooldown]);

  async function submitReset(email: string) {
    setRateLimited(false);
    try {
      // Always succeeds from the caller's perspective — the API never
      // reveals whether the email is registered (docs/AUTH_UX_AUDIT.md §3),
      // preventing account enumeration through this form.
      await apiFetch("/api/v1/auth/forgot-password", { method: "POST", body: { email } });
      setSubmittedEmail(email);
      setResendCooldown(RESEND_COOLDOWN_SECONDS);
    } catch (error) {
      if (error instanceof ApiError && error.status === 429) {
        setRateLimited(true);
      }
      // Any other error is deliberately swallowed — the whole point of
      // this endpoint is that it never signals failure to the caller.
    }
  }

  async function onSubmit(values: FormValues) {
    await submitReset(values.email);
  }

  if (submittedEmail) {
    return (
      <AuthLayout>
        <AuthCard title="Check your email">
          <div className="flex flex-col gap-4">
            <p className="text-sm text-[var(--fg-muted)]">
              If an account exists for <span className="font-medium text-[var(--fg-default)]">{submittedEmail}</span>,
              we&apos;ve sent a password reset link. It expires in 2 hours.
            </p>
            {rateLimited && (
              <AuthAlert variant="error">Too many attempts. Please wait a moment and try again.</AuthAlert>
            )}
            <Button
              type="button"
              variant="outline"
              disabled={resendCooldown > 0}
              onClick={() => submitReset(submittedEmail)}
            >
              {resendCooldown > 0 ? `Resend email (${resendCooldown}s)` : "Resend email"}
            </Button>
            <p className="text-center text-sm text-[var(--fg-muted)]">
              <Link href="/login" className="text-[var(--fg-default)] hover:underline">
                Back to sign in
              </Link>
            </p>
          </div>
        </AuthCard>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <AuthCard title="Reset your password" description="Enter your email and we'll send you a reset link.">
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <AuthField
            label="Email"
            type="email"
            autoComplete="email"
            error={errors.email?.message}
            {...register("email")}
          />
          {rateLimited && (
            <AuthAlert variant="error">Too many attempts. Please wait a moment and try again.</AuthAlert>
          )}
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Sending…" : "Send reset link"}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm text-[var(--fg-muted)]">
          <Link href="/login" className="text-[var(--fg-default)] hover:underline">
            Back to sign in
          </Link>
        </p>
      </AuthCard>
    </AuthLayout>
  );
}
