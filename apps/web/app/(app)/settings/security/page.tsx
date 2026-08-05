"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, apiFetch } from "@/lib/api";
import type { User } from "@/lib/types";

function extractSecret(provisioningUri: string): string {
  const match = /[?&]secret=([^&]+)/.exec(provisioningUri);
  return match ? decodeURIComponent(match[1]) : provisioningUri;
}

export default function SecuritySettingsPage() {
  const queryClient = useQueryClient();
  const [provisioningUri, setProvisioningUri] = useState<string | null>(null);
  const [confirmCode, setConfirmCode] = useState("");
  const [disableCode, setDisableCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: user, isLoading } = useQuery<User>({
    queryKey: ["auth", "me"],
    queryFn: () => apiFetch<User>("/api/v1/auth/me"),
  });

  const resendVerification = useMutation({
    mutationFn: () => apiFetch("/api/v1/auth/resend-verification-email", { method: "POST" }),
  });

  const enroll = useMutation({
    mutationFn: () => apiFetch<{ provisioning_uri: string }>("/api/v1/auth/mfa/enroll", { method: "POST" }),
    onSuccess: (result) => {
      setProvisioningUri(result.provisioning_uri);
      setError(null);
    },
  });

  const confirm = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/auth/mfa/confirm", { method: "POST", body: { code: confirmCode } }),
    onSuccess: () => {
      setProvisioningUri(null);
      setConfirmCode("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Invalid code"),
  });

  const disable = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/auth/mfa/disable", { method: "POST", body: { code: disableCode } }),
    onSuccess: () => {
      setDisableCode("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Invalid code"),
  });

  return (
    <div>
      <PageHeader
        title="Security"
        description="Email verification and two-factor authentication for your account."
      />

      {isLoading && <p className="text-sm text-[var(--fg-muted)]">Loading…</p>}

      {user && (
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Email verification</CardTitle>
            </CardHeader>
            <CardContent className="flex items-center justify-between pt-0">
              <Badge variant={user.email_verified_at ? "success" : "outline"}>
                {user.email_verified_at ? "Verified" : "Not verified"}
              </Badge>
              {!user.email_verified_at && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={resendVerification.isPending}
                  onClick={() => resendVerification.mutate()}
                >
                  {resendVerification.isSuccess ? "Sent" : "Resend verification email"}
                </Button>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Two-factor authentication (TOTP)</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4 pt-0">
              <Badge variant={user.mfa_enabled ? "success" : "outline"} className="w-fit">
                {user.mfa_enabled ? "Enabled" : "Disabled"}
              </Badge>

              {!user.mfa_enabled && !provisioningUri && (
                <Button
                  className="w-fit"
                  disabled={enroll.isPending}
                  onClick={() => enroll.mutate()}
                >
                  Enable two-factor authentication
                </Button>
              )}

              {!user.mfa_enabled && provisioningUri && (
                <div className="flex flex-col gap-3">
                  <p className="text-sm text-[var(--fg-muted)]">
                    Add this key to your authenticator app (Google Authenticator, 1Password,
                    etc.), then enter the 6-digit code it generates.
                  </p>
                  <code className="break-all rounded bg-[var(--gray-100)] p-2 text-xs">
                    {extractSecret(provisioningUri)}
                  </code>
                  <div className="flex gap-2">
                    <Input
                      placeholder="6-digit code"
                      value={confirmCode}
                      onChange={(e) => setConfirmCode(e.target.value)}
                      className="max-w-[160px]"
                    />
                    <Button disabled={!confirmCode.trim() || confirm.isPending} onClick={() => confirm.mutate()}>
                      Confirm
                    </Button>
                  </div>
                </div>
              )}

              {user.mfa_enabled && (
                <div className="flex flex-col gap-2">
                  <Label htmlFor="disable-code">Enter a code to disable two-factor authentication</Label>
                  <div className="flex gap-2">
                    <Input
                      id="disable-code"
                      placeholder="6-digit code"
                      value={disableCode}
                      onChange={(e) => setDisableCode(e.target.value)}
                      className="max-w-[160px]"
                    />
                    <Button
                      variant="destructive"
                      disabled={!disableCode.trim() || disable.isPending}
                      onClick={() => disable.mutate()}
                    >
                      Disable
                    </Button>
                  </div>
                </div>
              )}

              {error && <p className="text-sm text-[var(--critical-600)]">{error}</p>}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
