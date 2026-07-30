"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { ICPProfile } from "@/lib/types";

function ICPForm({ profile }: { profile: ICPProfile | null }) {
  const queryClient = useQueryClient();
  const [industries, setIndustries] = useState(profile?.target_industries.join(", ") ?? "");
  const [minCount, setMinCount] = useState(profile?.min_employee_count?.toString() ?? "");
  const [maxCount, setMaxCount] = useState(profile?.max_employee_count?.toString() ?? "");

  const save = useMutation({
    mutationFn: () =>
      apiFetch<ICPProfile>("/api/v1/sales/icp-profile", {
        method: "PUT",
        body: {
          target_industries: industries
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          min_employee_count: minCount ? Number(minCount) : null,
          max_employee_count: maxCount ? Number(maxCount) : null,
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sales", "icp-profile"] });
      queryClient.invalidateQueries({ queryKey: ["sales", "accounts"] });
      queryClient.invalidateQueries({ queryKey: ["sales", "intelligence"] });
    },
  });

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 pt-6">
        <div>
          <label className="mb-1 block text-sm text-neutral-700">
            Target industries (comma-separated, leave blank for &ldquo;any&rdquo;)
          </label>
          <Input
            value={industries}
            onChange={(e) => setIndustries(e.target.value)}
            placeholder="fintech, saas, healthcare"
          />
        </div>
        <div className="flex gap-4">
          <div>
            <label className="mb-1 block text-sm text-neutral-700">Min employee count</label>
            <Input type="number" value={minCount} onChange={(e) => setMinCount(e.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-sm text-neutral-700">Max employee count</label>
            <Input type="number" value={maxCount} onChange={(e) => setMaxCount(e.target.value)} />
          </div>
        </div>
        <Button disabled={save.isPending} onClick={() => save.mutate()} className="self-start">
          Save &amp; Rescore Accounts
        </Button>
        {save.isSuccess && (
          <p className="text-sm text-neutral-500">
            Saved — every existing Account has been rescored against this profile.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export default function ICPBuilderPage() {
  const { data: profile, isLoading } = useQuery<ICPProfile | null>({
    queryKey: ["sales", "icp-profile"],
    queryFn: () => apiFetch<ICPProfile | null>("/api/v1/sales/icp-profile"),
  });

  return (
    <div>
      <PageHeader
        title="ICP Builder"
        description="Define your Ideal Customer Profile — saving it immediately rescores every Account (spec §20)."
      />
      {isLoading ? (
        <p className="text-sm text-neutral-500">Loading…</p>
      ) : (
        <ICPForm key={profile?.id ?? "new"} profile={profile ?? null} />
      )}
    </div>
  );
}
