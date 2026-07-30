"use client";

import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import type { SalesContact, SequenceDetail } from "@/lib/types";

export default function SequenceDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();

  const { data: sequence } = useQuery<SequenceDetail>({
    queryKey: ["sales", "sequences", id],
    queryFn: () => apiFetch<SequenceDetail>(`/api/v1/sales/sequences/${id}`),
  });
  const { data: contacts } = useQuery<SalesContact[]>({
    queryKey: ["sales", "contacts"],
    queryFn: () => apiFetch<SalesContact[]>("/api/v1/sales/contacts"),
  });

  const [waitDays, setWaitDays] = useState("0");
  const [body, setBody] = useState("");
  const [selectedContactId, setSelectedContactId] = useState("");

  const addStep = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/sales/sequences/${id}/steps`, {
        method: "POST",
        body: { wait_days: Number(waitDays), channel: "email", body_template: body },
      }),
    onSuccess: () => {
      setBody("");
      setWaitDays("0");
      queryClient.invalidateQueries({ queryKey: ["sales", "sequences", id] });
    },
  });

  const enroll = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/sales/sequences/${id}/enroll`, {
        method: "POST",
        body: { contact_ids: [selectedContactId] },
      }),
    onSuccess: () => {
      setSelectedContactId("");
      queryClient.invalidateQueries({ queryKey: ["sales", "sequences", id] });
    },
  });

  if (!sequence) return null;

  const enrolledIds = new Set(sequence.enrollments.map((e) => e.contact_id));
  const availableContacts = contacts?.filter((c) => !enrolledIds.has(c.id)) ?? [];

  return (
    <div>
      <PageHeader
        title={sequence.name}
        description="Sequence Builder — steps fire in order, gated by the same compliance check as a manual send."
        actions={<StatusBadge status={sequence.status} />}
      />

      <div className="mb-8">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Steps
        </h2>
        <Card className="mb-3">
          <CardContent className="flex flex-col gap-2 pt-6">
            <div className="flex items-center gap-2">
              <label className="text-sm text-neutral-700">Wait days before this step:</label>
              <Input
                type="number"
                className="w-24"
                value={waitDays}
                onChange={(e) => setWaitDays(e.target.value)}
              />
            </div>
            <Textarea
              placeholder="Message body — use {{first_name}} for personalization"
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
            <Button
              size="sm"
              disabled={!body.trim() || addStep.isPending}
              onClick={() => addStep.mutate()}
              className="self-start"
            >
              Add step
            </Button>
          </CardContent>
        </Card>
        <div className="flex flex-col gap-2">
          {sequence.steps.map((step) => (
            <Card key={step.id}>
              <CardContent className="pt-6">
                <div className="mb-1 text-xs text-neutral-500">
                  Step {step.order_index + 1} — {step.wait_days} day(s) wait — {step.channel}
                </div>
                <p className="text-sm text-neutral-900">{step.body_template}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Enrollments
        </h2>
        {availableContacts.length > 0 && (
          <Card className="mb-3">
            <CardContent className="flex items-center gap-2 pt-6">
              <select
                className="h-9 flex-1 rounded-md border border-neutral-300 bg-white px-3 text-sm"
                value={selectedContactId}
                onChange={(e) => setSelectedContactId(e.target.value)}
              >
                <option value="">Select a contact to enroll…</option>
                {availableContacts.map((contact) => (
                  <option key={contact.id} value={contact.id}>
                    {contact.full_name}
                  </option>
                ))}
              </select>
              <Button
                size="sm"
                disabled={!selectedContactId || enroll.isPending}
                onClick={() => enroll.mutate()}
              >
                Enroll
              </Button>
            </CardContent>
          </Card>
        )}
        {sequence.enrollments.length === 0 && (
          <p className="text-sm text-neutral-500">No contacts enrolled yet.</p>
        )}
        <div className="flex flex-col gap-2">
          {sequence.enrollments.map((enrollment) => (
            <Card key={enrollment.id}>
              <CardContent className="flex items-center justify-between pt-6">
                <div className="text-sm text-neutral-900">
                  Step {enrollment.current_step_index + 1}
                </div>
                <StatusBadge status={enrollment.status} />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
