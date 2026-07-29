"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api";
import { useCurrentOrganization } from "@/lib/session";
import type { Organization } from "@/lib/types";

export default function OrganizationSettingsPage() {
  const queryClient = useQueryClient();
  const { data: organization } = useCurrentOrganization();
  const [draftName, setDraftName] = useState<string | null>(null);
  const name = draftName ?? organization?.name ?? "";

  const update = useMutation({
    mutationFn: (newName: string) =>
      apiFetch<Organization>("/api/v1/organizations/current", {
        method: "PATCH",
        body: { name: newName },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["organizations", "current"] }),
  });

  return (
    <div>
      <PageHeader title="Organization" description="Basic organization profile." />
      <Card className="max-w-md">
        <CardContent className="flex flex-col gap-4 pt-6">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="org-name">Name</Label>
            <Input id="org-name" value={name} onChange={(e) => setDraftName(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Slug</Label>
            <Input value={organization?.slug ?? ""} disabled />
          </div>
          <Button
            className="self-start"
            disabled={!name.trim() || update.isPending}
            onClick={() => update.mutate(name.trim())}
          >
            {update.isPending ? "Saving…" : "Save"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
