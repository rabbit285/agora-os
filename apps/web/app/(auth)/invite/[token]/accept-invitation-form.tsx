"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AuthAlert } from "@/components/auth/auth-alert";
import { AuthCard } from "@/components/auth/auth-card";
import { AuthField } from "@/components/auth/auth-field";
import { AuthLayout } from "@/components/auth/auth-layout";
import { InvitationSummary } from "@/components/auth/invitation-summary";
import { PasswordField } from "@/components/auth/password-field";
import { PasswordStrength } from "@/components/auth/password-strength";
import { VerificationState } from "@/components/auth/verification-state";
import { Button } from "@/components/ui/button";
import { ApiError, apiFetch } from "@/lib/api";
import { useCurrentUser } from "@/lib/session";
import type { InvitationPreview } from "@/lib/types";

const newAccountSchema = z.object({
  full_name: z.string().min(1, "Your name is required"),
  password: z.string().min(12, "Must be at least 12 characters"),
});
type NewAccountValues = z.infer<typeof newAccountSchema>;

export function AcceptInvitationForm({ token }: { token: string }) {
  const router = useRouter();
  const { data: currentUser } = useCurrentUser();
  const [serverError, setServerError] = useState<string | null>(null);
  const [accepting, setAccepting] = useState(false);
  const [declined, setDeclined] = useState(false);

  const {
    data: preview,
    isLoading,
    isError,
  } = useQuery<InvitationPreview>({
    queryKey: ["auth", "invitation-preview", token],
    queryFn: () => apiFetch<InvitationPreview>(`/api/v1/auth/invitations/${token}`),
    retry: false,
  });

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<NewAccountValues>({ resolver: zodResolver(newAccountSchema) });
  const password = watch("password") ?? "";

  async function acceptAsNewAccount(values: NewAccountValues) {
    setServerError(null);
    try {
      await apiFetch("/api/v1/auth/accept-invitation", {
        method: "POST",
        body: { token, full_name: values.full_name, password: values.password },
      });
      router.push("/dashboard");
    } catch (error) {
      setServerError(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
    }
  }

  async function acceptAsExistingAccount() {
    setAccepting(true);
    setServerError(null);
    try {
      await apiFetch("/api/v1/auth/accept-invitation", { method: "POST", body: { token } });
      router.push("/dashboard");
    } catch (error) {
      setServerError(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
      setAccepting(false);
    }
  }

  async function decline() {
    setAccepting(true);
    try {
      await apiFetch(`/api/v1/auth/invitations/${token}/decline`, { method: "POST" });
      setDeclined(true);
    } catch (error) {
      setServerError(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
      setAccepting(false);
    }
  }

  if (isLoading) {
    return (
      <AuthLayout>
        <AuthCard title="Invitation">
          <VerificationState status="pending" title="Loading your invitation…" />
        </AuthCard>
      </AuthLayout>
    );
  }

  if (isError || !preview) {
    return (
      <AuthLayout>
        <AuthCard title="Invitation not found">
          <VerificationState
            status="error"
            title="We couldn't find this invitation"
            description="Double check the link, or ask whoever invited you to send a new one."
            action={
              <Button asChild className="mt-2">
                <Link href="/login">Back to sign in</Link>
              </Button>
            }
          />
        </AuthCard>
      </AuthLayout>
    );
  }

  if (declined) {
    return (
      <AuthLayout>
        <AuthCard title="Invitation declined">
          <VerificationState status="success" title="You've declined this invitation" description="No account was created." />
        </AuthCard>
      </AuthLayout>
    );
  }

  if (preview.status === "expired") {
    return (
      <AuthLayout>
        <AuthCard title="Invitation expired">
          <VerificationState
            status="error"
            title="This invitation has expired"
            description={`Ask an admin at ${preview.organization_name} to send you a new one.`}
          />
        </AuthCard>
      </AuthLayout>
    );
  }

  if (preview.status === "revoked") {
    return (
      <AuthLayout>
        <AuthCard title="Invitation revoked">
          <VerificationState
            status="error"
            title="This invitation is no longer valid"
            description="It was revoked or already declined."
          />
        </AuthCard>
      </AuthLayout>
    );
  }

  if (preview.status === "accepted") {
    return (
      <AuthLayout>
        <AuthCard title="Already accepted">
          <VerificationState
            status="success"
            title="This invitation has already been accepted"
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

  const roleLabel = preview.role_key.replace(/_/g, " ");
  const expiresLabel = new Date(preview.expires_at).toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <AuthLayout>
      <AuthCard title="You've been invited">
        <div className="flex flex-col gap-4">
          <InvitationSummary
            organizationName={preview.organization_name}
            invitedEmail={preview.email}
            roleLabel={roleLabel}
            expiresAt={expiresLabel}
            inviterName={preview.inviter_name ?? undefined}
          />

          {preview.account_exists ? (
            currentUser ? (
              <>
                <p className="text-sm text-[var(--fg-muted)]">
                  You&apos;re signed in as {currentUser.email}. Accept to join{" "}
                  {preview.organization_name}.
                </p>
                {serverError && <AuthAlert variant="error">{serverError}</AuthAlert>}
                <div className="flex gap-2">
                  <Button onClick={acceptAsExistingAccount} disabled={accepting} className="flex-1">
                    {accepting ? "Joining…" : "Accept"}
                  </Button>
                  <Button variant="outline" onClick={decline} disabled={accepting}>
                    Decline
                  </Button>
                </div>
              </>
            ) : (
              <>
                <p className="text-sm text-[var(--fg-muted)]">
                  An account already exists for {preview.email}. Sign in to accept this invitation.
                </p>
                <Button asChild>
                  <Link href={`/login?redirect=${encodeURIComponent(`/invite/${token}`)}`}>
                    Sign in to accept
                  </Link>
                </Button>
              </>
            )
          ) : (
            <form className="flex flex-col gap-4" onSubmit={handleSubmit(acceptAsNewAccount)} noValidate>
              <AuthField
                label="Your name"
                autoComplete="name"
                error={errors.full_name?.message}
                {...register("full_name")}
              />
              <div className="flex flex-col gap-1.5">
                <PasswordField
                  label="Set a password"
                  autoComplete="new-password"
                  error={errors.password?.message}
                  {...register("password")}
                />
                {password.length > 0 && <PasswordStrength password={password} />}
              </div>
              {serverError && <AuthAlert variant="error">{serverError}</AuthAlert>}
              <div className="flex gap-2">
                <Button type="submit" disabled={isSubmitting} className="flex-1">
                  {isSubmitting ? "Joining…" : "Accept and join"}
                </Button>
                <Button type="button" variant="outline" onClick={decline} disabled={accepting}>
                  Decline
                </Button>
              </div>
            </form>
          )}
        </div>
      </AuthCard>
    </AuthLayout>
  );
}
