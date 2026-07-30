"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, apiFetch } from "@/lib/api";

const schema = z.object({
  code: z.string().min(6, "Enter the 6-digit code").max(8),
});
type FormValues = z.infer<typeof schema>;

export default function MfaChallengePage() {
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
      await apiFetch("/api/v1/auth/mfa/verify", { method: "POST", body: values });
      router.push("/");
    } catch (error) {
      setServerError(error instanceof ApiError ? error.message : "Invalid code");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Two-factor verification</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-4 text-sm text-neutral-500">
          Enter the 6-digit code from your authenticator app.
        </p>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="code">Code</Label>
            <Input
              id="code"
              inputMode="numeric"
              autoComplete="one-time-code"
              autoFocus
              {...register("code")}
            />
            {errors.code && <p className="text-xs text-red-600">{errors.code.message}</p>}
          </div>
          {serverError && <p className="text-sm text-red-600">{serverError}</p>}
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Verifying…" : "Verify"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
