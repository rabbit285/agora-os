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
import { PasswordStrength } from "@/components/auth/password-strength";
import { Button } from "@/components/ui/button";
import { track } from "@/lib/analytics";
import { ApiError, apiFetch } from "@/lib/api";
import { isSafeRedirectTarget } from "@/lib/auth-redirect";

// Only what the backend's SignupRequest actually accepts (email,
// password, full_name, organization_name, marketing_consent) is
// collected — no company size, industry, or phone number before a
// visitor can even try the product (docs/AUTH_UX_AUDIT.md §3). Country
// isn't collected either: the backend has no field for it, and adding a
// UI field with nowhere real to send it would be exactly the kind of
// decorative form control this effort's brief explicitly warns against.
const schema = z
  .object({
    full_name: z.string().min(1, "Your name is required"),
    organization_name: z.string().min(1, "Organization name is required"),
    email: z.string().email("Enter a valid work email"),
    password: z.string().min(12, "Must be at least 12 characters"),
    confirm_password: z.string().min(1, "Please confirm your password"),
    accept_terms: z.boolean().refine((v) => v, "You must accept the Terms and Privacy Policy"),
    marketing_consent: z.boolean(),
  })
  .refine((values) => values.password === values.confirm_password, {
    message: "Passwords don't match",
    path: ["confirm_password"],
  });

type FormValues = z.infer<typeof schema>;

function SignupForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { accept_terms: false, marketing_consent: false },
  });
  const password = watch("password") ?? "";

  const requestedRedirect = searchParams.get("redirect");
  const safeRedirect = isSafeRedirectTarget(requestedRedirect) ? requestedRedirect : null;

  async function onSubmit(values: FormValues) {
    setServerError(null);
    track("signup_started");
    try {
      await apiFetch("/api/v1/auth/signup", {
        method: "POST",
        body: {
          full_name: values.full_name,
          organization_name: values.organization_name,
          email: values.email,
          password: values.password,
          marketing_consent: values.marketing_consent,
        },
      });
      track("signup_completed");
      // Every new organization starts with the guided onboarding wizard
      // (spec §68), not straight to the dashboard — the redirect-back
      // target (if any) is honored only after onboarding completes.
      const onboardingUrl = safeRedirect
        ? `/onboarding?redirect=${encodeURIComponent(safeRedirect)}`
        : "/onboarding";
      router.push(onboardingUrl);
    } catch (error) {
      if (error instanceof ApiError && error.status === 429) {
        setServerError("Too many attempts. Please wait a moment and try again.");
      } else {
        setServerError(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
      }
    }
  }

  return (
    <AuthCard title="Create your secure workspace" description="Start with guided setup.">
      <div className="flex flex-col gap-4">
        <OAuthButtons />
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <AuthField
            label="Full name"
            autoComplete="name"
            error={errors.full_name?.message}
            {...register("full_name")}
          />
          <AuthField
            label="Work email"
            type="email"
            autoComplete="email"
            error={errors.email?.message}
            {...register("email")}
          />
          <AuthField
            label="Organization name"
            autoComplete="organization"
            error={errors.organization_name?.message}
            {...register("organization_name")}
          />
          <div className="flex flex-col gap-1.5">
            <PasswordField
              label="Password"
              autoComplete="new-password"
              error={errors.password?.message}
              {...register("password")}
            />
            {password.length > 0 && <PasswordStrength password={password} />}
          </div>
          <PasswordField
            label="Confirm password"
            autoComplete="new-password"
            error={errors.confirm_password?.message}
            {...register("confirm_password")}
          />

          <label className="flex items-start gap-2 text-xs text-[var(--fg-muted)]">
            <input
              type="checkbox"
              className="mt-0.5"
              aria-invalid={errors.accept_terms ? "true" : undefined}
              {...register("accept_terms")}
            />
            <span>
              I agree to the{" "}
              <Link href="/terms" className="underline hover:text-[var(--fg-default)]" target="_blank">
                Terms of Service
              </Link>{" "}
              and{" "}
              <Link href="/privacy" className="underline hover:text-[var(--fg-default)]" target="_blank">
                Privacy Policy
              </Link>
              .
            </span>
          </label>
          {errors.accept_terms && (
            <p role="alert" className="-mt-2 text-xs text-[var(--critical-600)]">
              {errors.accept_terms.message}
            </p>
          )}

          {/* Deliberately a separate, unchecked-by-default control — never
              bundled into Terms/Privacy acceptance. */}
          <label className="flex items-start gap-2 text-xs text-[var(--fg-muted)]">
            <input type="checkbox" className="mt-0.5" {...register("marketing_consent")} />
            <span>Send me occasional product updates. You can unsubscribe anytime.</span>
          </label>

          {serverError && <AuthAlert variant="error">{serverError}</AuthAlert>}
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Creating account…" : "Start free"}
          </Button>
        </form>
        <p className="text-center text-sm text-[var(--fg-muted)]">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-[var(--fg-default)] hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </AuthCard>
  );
}

export default function SignupPage() {
  return (
    <AuthLayout>
      <Suspense fallback={null}>
        <SignupForm />
      </Suspense>
    </AuthLayout>
  );
}
