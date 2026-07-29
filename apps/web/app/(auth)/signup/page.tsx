"use client";

import Link from "next/link";
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
  full_name: z.string().min(1, "Your name is required"),
  organization_name: z.string().min(1, "Organization name is required"),
  email: z.string().email(),
  password: z.string().min(12, "Must be at least 12 characters"),
});

type FormValues = z.infer<typeof schema>;

export default function SignupPage() {
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
      await apiFetch("/api/v1/auth/signup", { method: "POST", body: values });
      router.push("/");
    } catch (error) {
      setServerError(error instanceof ApiError ? error.message : "Something went wrong");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create your organization</CardTitle>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="full_name">Your name</Label>
            <Input id="full_name" autoComplete="name" {...register("full_name")} />
            {errors.full_name && <p className="text-xs text-red-600">{errors.full_name.message}</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="organization_name">Organization name</Label>
            <Input id="organization_name" {...register("organization_name")} />
            {errors.organization_name && (
              <p className="text-xs text-red-600">{errors.organization_name.message}</p>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">Work email</Label>
            <Input id="email" type="email" autoComplete="email" {...register("email")} />
            {errors.email && <p className="text-xs text-red-600">{errors.email.message}</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" autoComplete="new-password" {...register("password")} />
            {errors.password && <p className="text-xs text-red-600">{errors.password.message}</p>}
          </div>
          {serverError && <p className="text-sm text-red-600">{serverError}</p>}
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Creating account…" : "Create account"}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm text-neutral-500">
          Already have an account?{" "}
          <Link href="/login" className="text-neutral-900 hover:underline">
            Log in
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
