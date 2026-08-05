"use client";

import { useMutation, useQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";

type SsoProviderStatus = { provider: string; configured: boolean };

const SSO_LABELS: Record<string, string> = { google: "Google", microsoft: "Microsoft" };

/** Real Google/Microsoft SSO login (docs/AUTH_UX_AUDIT.md §3) — buttons
 * only render for providers GET /auth/sso/providers reports as configured;
 * an unconfigured provider is never shown, never a disabled placeholder.
 * Shared by both /login and /signup, since a first-time SSO login
 * provisions a new org exactly like signup does server-side. */
export function OAuthButtons() {
  const { data: providers } = useQuery<SsoProviderStatus[]>({
    queryKey: ["auth", "sso", "providers"],
    queryFn: () => apiFetch<SsoProviderStatus[]>("/api/v1/auth/sso/providers"),
  });

  const startSso = useMutation({
    mutationFn: (provider: string) =>
      apiFetch<{ authorization_url: string }>(`/api/v1/auth/sso/${provider}/start`),
    onSuccess: (data) => {
      window.location.href = data.authorization_url;
    },
  });

  const configured = providers?.filter((p) => p.configured) ?? [];
  if (configured.length === 0) return null;

  return (
    <div className="flex flex-col gap-2">
      {configured.map((p) => (
        <Button
          key={p.provider}
          type="button"
          variant="outline"
          disabled={startSso.isPending}
          onClick={() => startSso.mutate(p.provider)}
        >
          Continue with {SSO_LABELS[p.provider] ?? p.provider}
        </Button>
      ))}
      <div className="flex items-center gap-2 text-xs text-[var(--fg-subtle)]">
        <div className="h-px flex-1 bg-[var(--border-default)]" />
        or
        <div className="h-px flex-1 bg-[var(--border-default)]" />
      </div>
    </div>
  );
}
