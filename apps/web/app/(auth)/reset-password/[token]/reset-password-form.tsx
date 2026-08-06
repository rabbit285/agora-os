"use client";

import { useState } from "react";
import Link from "next/link";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AuthAlert } from "@/components/auth/auth-alert";
import { AuthCard } from "@/components/auth/auth-card";
import { AuthLayout } from "@/components/auth/auth-layout";
import { PasswordField } from "@/components/auth/password-field";
import { PasswordStrength } from "@/components/auth/password-strength";
import { VerificationState } from "@/components/auth/verification-state";
import { Button } from "@/components/ui/button";
import { ApiError, apiFetch } from "@/lib/api";

const schema = z
  .object({
    new_password: z.string().min(12, "Must be at least 12 characters"),
    confirm_password: z.string().min(1, "Please confirm your password"),
  })
  .refine((values) => values.new_password === values.confirm_password, {
    message: "Passwords don't match",
    path: ["confirm_password"],
  });

type FormValues = z.infer<typeof schema>;

type Status = "form" | "success" | "invalid-or-expired";

export function ResetPasswordForm({ token }: { token: string }) {
  const [status, setStatus] = useState<Status>("form");
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });
  const password = watch("new_password") ?? "";

  async function onSubmit(values: FormValues) {
    setServerError(null);
    try {
      await apiFetch("/api/v1/auth/reset-password", {
        method: "POST",
        body: { token, new_password: values.new_password },
      });
      setStatus("success");
    } catch (error) {
      if (error instanceof ApiError && error.status === 429) {
        setServerError("Too many attempts. Please wait a moment and try again.");
        return;
      }
      // The backend deliberately returns one undifferentiated message for
      // both an invalid and an expired token (docs/AUTH_UX_AUDIT.md §3) —
      // this UI reflects that single real signal rather than fabricating
      // a distinction the API can't actually make.
      if (error instanceof ApiError && error.status === 400) {
        setStatus("invalid-or-expired");
        return;
      }
      setServerError(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
    }
  }

  if (status === "success") {
    return (
      <AuthLayout>
        <AuthCard title="Password updated">
          <VerificationState
            status="success"
            title="Your password has been changed"
            description="For your security, you've been signed out everywhere else."
            action={
              <Button asChild className="mt-2">
                <Link href="/login">Sign in</Link>
              </Button>
            }
          />
        </AuthCard>
      </AuthLayout>
    );
  }

  if (status === "invalid-or-expired") {
    return (
      <AuthLayout>
        <AuthCard title="Link invalid or expired">
          <VerificationState
            status="error"
            title="This reset link no longer works"
            description="It may have already been used or its 2-hour window has passed."
            action={
              <Button asChild className="mt-2">
                <Link href="/forgot-password">Request a new link</Link>
              </Button>
            }
          />
        </AuthCard>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <AuthCard title="Set a new password">
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="flex flex-col gap-1.5">
            <PasswordField
              label="New password"
              autoComplete="new-password"
              error={errors.new_password?.message}
              {...register("new_password")}
            />
            {password.length > 0 && <PasswordStrength password={password} />}
          </div>
          <PasswordField
            label="Confirm password"
            autoComplete="new-password"
            error={errors.confirm_password?.message}
            {...register("confirm_password")}
          />
          {serverError && <AuthAlert variant="error">{serverError}</AuthAlert>}
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Saving…" : "Save new password"}
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
