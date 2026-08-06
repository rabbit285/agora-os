"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AuthAlert } from "@/components/auth/auth-alert";
import { AuthCard } from "@/components/auth/auth-card";
import { AuthField } from "@/components/auth/auth-field";
import { AuthLayout } from "@/components/auth/auth-layout";
import { Button } from "@/components/ui/button";
import { ApiError, apiFetch } from "@/lib/api";
import { isSafeRedirectTarget } from "@/lib/auth-redirect";

const schema = z.object({
  code: z.string().min(6, "Enter the 6-digit code").max(8),
});
type FormValues = z.infer<typeof schema>;

function MfaChallengeForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  async function onSubmit(values: FormValues) {
    setServerError(null);
    try {
      await apiFetch("/api/v1/auth/mfa/verify", { method: "POST", body: values });
      const requestedRedirect = searchParams.get("redirect");
      router.push(isSafeRedirectTarget(requestedRedirect) ? requestedRedirect : "/dashboard");
    } catch (error) {
      if (error instanceof ApiError && error.status === 429) {
        setServerError("Too many attempts. Please wait a moment and try again.");
      } else {
        setServerError(error instanceof ApiError ? error.message : "Invalid code");
      }
    }
  }

  return (
    <AuthCard title="Two-factor verification" description="Enter the 6-digit code from your authenticator app.">
      <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        <AuthField
          label="Code"
          inputMode="numeric"
          autoComplete="one-time-code"
          autoFocus
          error={errors.code?.message}
          {...register("code")}
        />
        {serverError && <AuthAlert variant="error">{serverError}</AuthAlert>}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Verifying…" : "Verify"}
        </Button>
      </form>
    </AuthCard>
  );
}

export function MfaChallengeClient() {
  return (
    <AuthLayout>
      <Suspense fallback={null}>
        <MfaChallengeForm />
      </Suspense>
    </AuthLayout>
  );
}
