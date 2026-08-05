"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, apiFetch } from "@/lib/api";

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(1, "Password is required"),
});

type FormValues = z.infer<typeof schema>;

type SsoProviderStatus = { provider: string; configured: boolean };

const SSO_LABELS: Record<string, string> = { google: "Google", microsoft: "Microsoft" };

function SsoButtons() {
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
    <div className="mb-4 flex flex-col gap-2">
      {configured.map((p) => (
        <Button
          key={p.provider}
          variant="outline"
          disabled={startSso.isPending}
          onClick={() => startSso.mutate(p.provider)}
        >
          Sign in with {SSO_LABELS[p.provider] ?? p.provider}
        </Button>
      ))}
      <div className="flex items-center gap-2 text-xs text-[var(--fg-subtle)]">
        <div className="h-px flex-1 bg-[var(--gray-200)]" />
        or
        <div className="h-px flex-1 bg-[var(--gray-200)]" />
      </div>
    </div>
  );
}

function SsoErrorBanner() {
  const searchParams = useSearchParams();
  const ssoError = searchParams.get("error");
  if (!ssoError) return null;
  return <p className="mb-4 text-sm text-[var(--critical-600)]">{ssoError}</p>;
}

export default function LoginPage() {
  const router = useRouter();
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  async function onSubmit(values: FormValues) {
    setServerError(null);
    try {
      const result = await apiFetch<{ mfa_required: boolean }>("/api/v1/auth/login", {
        method: "POST",
        body: values,
      });
      router.push(result.mfa_required ? "/mfa-challenge" : "/");
    } catch (error) {
      setServerError(error instanceof ApiError ? error.message : "Something went wrong");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Log in</CardTitle>
      </CardHeader>
      <CardContent>
        <SsoButtons />
        <Suspense fallback={null}>
          <SsoErrorBanner />
        </Suspense>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" autoComplete="email" {...register("email")} />
            {errors.email && <p className="text-xs text-[var(--critical-600)]">{errors.email.message}</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="password">Password</Label>
              <Link href="/forgot-password" className="text-xs text-[var(--fg-muted)] hover:underline">
                Forgot password?
              </Link>
            </div>
            <Input id="password" type="password" autoComplete="current-password" {...register("password")} />
            {errors.password && <p className="text-xs text-[var(--critical-600)]">{errors.password.message}</p>}
          </div>
          {serverError && <p className="text-sm text-[var(--critical-600)]">{serverError}</p>}
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Logging in…" : "Log in"}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm text-[var(--fg-muted)]">
          No account?{" "}
          <Link href="/signup" className="text-[var(--fg-default)] hover:underline">
            Sign up
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
