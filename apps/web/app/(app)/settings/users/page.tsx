"use client";

import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { Membership } from "@/lib/types";

export default function UsersSettingsPage() {
  const { data: members, isLoading } = useQuery<Membership[]>({
    queryKey: ["organizations", "current", "members"],
    queryFn: () => apiFetch<Membership[]>("/api/v1/organizations/current/members"),
  });

  return (
    <div>
      <PageHeader
        title="Users"
        description="Members of this organization and their roles (spec section 54)."
      />
      {isLoading && <p className="text-sm text-neutral-500">Loading…</p>}
      <div className="flex flex-col gap-2">
        {members?.map((member) => (
          <Card key={member.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div className="font-mono text-xs text-neutral-500">{member.user_id}</div>
              <div className="flex gap-2">
                {member.roles.map((role) => (
                  <Badge key={role} variant="secondary">
                    {role.replace(/_/g, " ")}
                  </Badge>
                ))}
                <Badge variant={member.status === "active" ? "success" : "outline"}>
                  {member.status}
                </Badge>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
