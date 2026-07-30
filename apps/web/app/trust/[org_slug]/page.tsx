"use client";

import { use, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { TrustCenterPublic } from "@/lib/types";

const STATUS_LABELS: Record<string, string> = {
  planned: "Planned",
  in_progress: "In progress",
  implemented: "Implemented",
  independently_assessed: "Independently assessed",
  certified: "Certified",
};

function categoryLabel(category: string): string {
  return category
    .split("_")
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
}

export default function TrustCenterPublicPage({
  params,
}: {
  params: Promise<{ org_slug: string }>;
}) {
  const { org_slug: orgSlug } = use(params);
  const [requesterName, setRequesterName] = useState("");
  const [requesterEmail, setRequesterEmail] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [message, setMessage] = useState("");

  const { data: trustCenter, isLoading, isError } = useQuery<TrustCenterPublic>({
    queryKey: ["trust-center-public", orgSlug],
    queryFn: () => apiFetch<TrustCenterPublic>(`/api/v1/trust-center/public/${orgSlug}`),
  });

  const submitRequest = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/trust-center/public/${orgSlug}/evidence-requests`, {
        method: "POST",
        body: {
          requester_name: requesterName,
          requester_email: requesterEmail,
          company_name: companyName.trim() || null,
          message: message.trim() || null,
        },
      }),
    onSuccess: () => {
      setRequesterName("");
      setRequesterEmail("");
      setCompanyName("");
      setMessage("");
    },
  });

  if (isLoading) return null;

  if (isError || !trustCenter) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-16 text-center">
        <h1 className="text-xl font-semibold text-neutral-900">Trust Center not found</h1>
        <p className="mt-2 text-sm text-neutral-500">
          We couldn&apos;t find a public Trust Center at this address.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="text-3xl font-semibold text-neutral-900">
        {trustCenter.organization_name} Trust Center
      </h1>
      <p className="mt-2 text-sm text-neutral-500">
        Security, privacy, and compliance information for {trustCenter.organization_name}.
      </p>

      <div className="mt-10 flex flex-col gap-4">
        {trustCenter.items.length === 0 && (
          <p className="text-sm text-neutral-500">No information has been published yet.</p>
        )}
        {trustCenter.items.map((item) => (
          <Card key={item.category}>
            <CardContent className="flex flex-col gap-2 pt-6">
              <div className="flex items-center justify-between">
                <div className="font-medium text-neutral-900">
                  {item.title || categoryLabel(item.category)}
                </div>
                <Badge variant="secondary">{STATUS_LABELS[item.status] ?? item.status}</Badge>
              </div>
              {item.content && <p className="text-sm text-neutral-700">{item.content}</p>}
              {item.policy && (
                <div className="text-xs text-neutral-500">
                  Downloadable document: {item.policy.title}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="mt-12">
        <h2 className="mb-3 text-lg font-semibold text-neutral-900">Request Evidence</h2>
        <p className="mb-4 text-sm text-neutral-500">
          Need a document or answer that isn&apos;t published here? Send us a request and our
          team will follow up.
        </p>
        <Card>
          <CardContent className="flex flex-col gap-2 pt-6">
            <Input
              placeholder="Your name"
              value={requesterName}
              onChange={(e) => setRequesterName(e.target.value)}
            />
            <Input
              placeholder="Your email"
              type="email"
              value={requesterEmail}
              onChange={(e) => setRequesterEmail(e.target.value)}
            />
            <Input
              placeholder="Company (optional)"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
            />
            <Input
              placeholder="What are you looking for? (optional)"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
            />
            <Button
              disabled={
                !requesterName.trim() || !requesterEmail.trim() || submitRequest.isPending
              }
              onClick={() => submitRequest.mutate()}
            >
              Submit request
            </Button>
            {submitRequest.isSuccess && (
              <p className="text-sm text-emerald-600">
                Thanks — we&apos;ve received your request and will be in touch.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
