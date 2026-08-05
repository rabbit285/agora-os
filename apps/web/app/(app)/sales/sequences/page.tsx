"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { ProcessDueStepsResult, Sequence } from "@/lib/types";

export default function SequencesPage() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");

  const { data: sequences } = useQuery<Sequence[]>({
    queryKey: ["sales", "sequences"],
    queryFn: () => apiFetch<Sequence[]>("/api/v1/sales/sequences"),
  });

  const createSequence = useMutation({
    mutationFn: (newName: string) =>
      apiFetch<Sequence>("/api/v1/sales/sequences", { method: "POST", body: { name: newName } }),
    onSuccess: () => {
      setName("");
      queryClient.invalidateQueries({ queryKey: ["sales", "sequences"] });
    },
  });

  const processDueSteps = useMutation({
    mutationFn: () =>
      apiFetch<ProcessDueStepsResult>("/api/v1/sales/sequences/process-due-steps", {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sales", "sequences"] });
      queryClient.invalidateQueries({ queryKey: ["sales", "inbox"] });
    },
  });

  return (
    <div>
      <PageHeader
        title="Sequences"
        description="Multi-step outreach cadences — every automated send is gated by the same compliance check as a manual one (spec §23)."
        actions={
          <Button
            variant="outline"
            size="sm"
            disabled={processDueSteps.isPending}
            onClick={() => processDueSteps.mutate()}
          >
            {processDueSteps.isPending ? "Processing…" : "Process due steps"}
          </Button>
        }
      />
      {processDueSteps.data && (
        <p className="mb-4 text-xs text-[var(--fg-muted)]">
          Processed {processDueSteps.data.processed} due step(s).
        </p>
      )}
      <Card className="mb-4">
        <CardContent className="flex gap-2 pt-6">
          <Input
            placeholder="New sequence name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && name.trim()) createSequence.mutate(name.trim());
            }}
          />
          <Button
            disabled={!name.trim() || createSequence.isPending}
            onClick={() => createSequence.mutate(name.trim())}
          >
            Create sequence
          </Button>
        </CardContent>
      </Card>
      {sequences?.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">No sequences yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {sequences?.map((sequence) => (
          <Link key={sequence.id} href={`/sales/sequences/${sequence.id}`}>
            <Card className="transition-colors hover:border-[var(--border-strong)]">
              <CardContent className="flex items-center justify-between pt-6">
                <div className="font-medium text-[var(--fg-default)]">{sequence.name}</div>
                <StatusBadge status={sequence.status} />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
