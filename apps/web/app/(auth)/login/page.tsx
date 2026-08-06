"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AuthAlert } from "@/components/auth/auth-alert";
import { AuthCard } from "@/components/auth/auth-card";
import { AuthField } from "@/components/auth/auth-field";
import { AuthLayout } from "@/components/auth/auth-layout";
import { OAuthButtons } from "@/components/auth/oauth-buttons";
import { PasswordField } from "@/components/auth/password-field";
import { Button } from "@/components/ui/button";
import { track } from "@/lib/analytics";
import { ApiError, apiFetch } from "@/lib/api";
import { isSafeRedirectTarget } from "@/lib/auth-redirect";

const schema = z.object({
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(1, "Password is required"),
});

type FormValues = z.infer<typeof schema>;

/** Reads the `?error=` the SSO callback attaches on failure
 * (apps/api/app/identity/router.py) — wrapped in Suspense because
 * useSearchParams() opts this subtree out of static rendering. */
function SsoErrorBanner() {
  const searchParams = useSearchParams();
  const ssoError = searchParams.get("error");
  if (!ssoError) return null;
  return <AuthAlert variant="error">{ssoError}</AuthAlert>;
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const requestedRedirect = searchParams.get("redirect");
  const safeRedirect = isSafeRedirectTarget(requestedRedirect) ? requestedRedirect : null;

  async function onSubmit(values: FormValues) {
    setServerError(null);
    try {
      const result = await apiFetch<{ mfa_required: boolean }>("/api/v1/auth/login", {
        method: "POST",
        body: values,
      });
      track("login_completed");
      if (result.mfa_required) {
        const mfaUrl = safeRedirect ? `/mfa-challenge?redirect=${encodeURIComponent(safeRedirect)}` : "/mfa-challenge";
        router.push(mfaUrl);
        return;
      }
      router.push(safeRedirect ?? "/dashboard");
    } catch (error) {
      if (error instanceof ApiError && error.status === 429) {
        setServerError("Too many attempts. Please wait a moment and try again.");
      } else {
        // The backend deliberately returns the same "Invalid email or
        // password" message for a wrong password, an unknown email, and
        // an inactive account (docs/AUTH_UX_AUDIT.md §3) — an account-
        // enumeration and account-disabled-leak prevention this page
        // preserves as-is rather than trying to be more specific.
        setServerError(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
      }
    }
  }

  return (
    <AuthCard title="Welcome back" description="Sign in to your workspace.">
      <div className="flex flex-col gap-4">
        <OAuthButtons />
        <Suspense fallback={null}>
          <SsoErrorBanner />
        </Suspense>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <AuthField
            label="Email"
            type="email"
            autoComplete="email"
            error={errors.email?.message}
            {...register("email")}
          />
          <PasswordField
            label="Password"
            autoComplete="current-password"
            error={errors.password?.message}
            action={
              <Link href="/forgot-password" className="text-xs text-[var(--fg-muted)] hover:underline">
                Forgot password?
              </Link>
            }
            {...register("password")}
          />
          {serverError && <AuthAlert variant="error">{serverError}</AuthAlert>}
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        <p className="text-center text-sm text-[var(--fg-muted)]">
          Don&apos;t have an account?{" "}
          <Link href="/signup" className="font-medium text-[var(--fg-default)] hover:underline">
            Start free
          </Link>
        </p>
      </div>
    </AuthCard>
  );
}

export default function LoginPage() {
  return (
    <AuthLayout>
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </AuthLayout>
  );
}
