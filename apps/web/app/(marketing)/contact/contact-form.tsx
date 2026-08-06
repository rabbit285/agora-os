"use client";

import { useState } from "react";
import Link from "next/link";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AuthAlert } from "@/components/auth/auth-alert";
import { AuthField } from "@/components/auth/auth-field";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiFetch } from "@/lib/api";
import { track } from "@/lib/analytics";

const schema = z.object({
  full_name: z.string().min(1, "Your name is required"),
  work_email: z.string().email("Enter a valid work email"),
  company_name: z.string().min(1, "Company name is required"),
  company_size: z.enum(["1-10", "11-50", "51-200", "201-500", "500+"]),
  country: z.string().min(1, "Country is required"),
  primary_interest: z.enum([
    "compliance",
    "security",
    "sales",
    "support",
    "automation",
    "ai_governance",
    "knowledge_management",
    "ai_copilot",
    "other",
  ]),
  message: z.string().max(2000).optional(),
});

type FormValues = z.infer<typeof schema>;

const INTEREST_LABELS: Record<FormValues["primary_interest"], string> = {
  compliance: "Compliance",
  security: "Security",
  sales: "Sales",
  support: "Customer Support",
  automation: "Workflow Automation",
  ai_governance: "AI Governance",
  knowledge_management: "Knowledge Management",
  ai_copilot: "AI Copilot",
  other: "Other",
};

/** Spam protection here is the same, already-real global mechanism every
 * other public endpoint in this codebase relies on — the IP-keyed
 * RateLimitMiddleware (docs/PUBLIC_SITE_AUDIT.md §5) — rather than a new
 * CAPTCHA dependency this codebase has no existing, approved integration
 * for. */
export function ContactForm() {
  const [submitted, setSubmitted] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  async function onSubmit(values: FormValues) {
    setServerError(null);
    try {
      await apiFetch("/api/v1/marketing/demo-requests", { method: "POST", body: values });
      track("demo_request_submitted", { primary_interest: values.primary_interest });
      setSubmitted(true);
    } catch (error) {
      setServerError(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
    }
  }

  if (submitted) {
    return (
      <AuthAlert variant="success">
        Thanks — we&apos;ve received your request and will be in touch shortly.
      </AuthAlert>
    );
  }

  return (
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
        error={errors.work_email?.message}
        {...register("work_email")}
      />
      <AuthField
        label="Company name"
        autoComplete="organization"
        error={errors.company_name?.message}
        {...register("company_name")}
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="company_size">Company size</Label>
          <Select id="company_size" {...register("company_size")}>
            <option value="1-10">1–10 employees</option>
            <option value="11-50">11–50 employees</option>
            <option value="51-200">51–200 employees</option>
            <option value="201-500">201–500 employees</option>
            <option value="500+">500+ employees</option>
          </Select>
        </div>
        <AuthField label="Country" autoComplete="country-name" error={errors.country?.message} {...register("country")} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="primary_interest">Primary interest</Label>
        <Select id="primary_interest" {...register("primary_interest")}>
          {Object.entries(INTEREST_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="message">Message (optional)</Label>
        <Textarea id="message" rows={4} {...register("message")} />
      </div>
      {serverError && <AuthAlert variant="error">{serverError}</AuthAlert>}
      <p className="text-xs text-[var(--fg-muted)]">
        By submitting, you agree to be contacted about Agora Origin. See our{" "}
        <Link href="/privacy" className="underline hover:text-[var(--fg-muted)]">
          Privacy Policy
        </Link>
        .
      </p>
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Sending…" : "Request a demo"}
      </Button>
    </form>
  );
}
