"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { Role } from "@/lib/types";

export default function RolesSettingsPage() {
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data: roles, isLoading, error } = useQuery<Role[]>({
    queryKey: ["organizations", "current", "roles"],
    queryFn: () => apiFetch<Role[]>("/api/v1/organizations/current/roles"),
  });

  return (
    <div>
      <PageHeader
        title="Roles"
        description="spec §54's default role list and each role's real granted permissions. These are
          system roles shared across every organization in this deployment, so this is a reference
          view, not an editor — assign a role to a member from Settings > Users."
      />

      {isLoading && <p className="text-sm text-[var(--fg-muted)]">Loading…</p>}
      {error && <p className="text-sm text-[var(--critical-600)]">Could not load roles.</p>}
      {roles && roles.length === 0 && <p className="text-sm text-[var(--fg-muted)]">No roles found.</p>}

      <div className="flex flex-col gap-2">
        {roles?.map((role) => {
          const isExpanded = expanded === role.key;
          return (
            <Card key={role.key}>
              <CardContent className="pt-6">
                <button
                  className="flex w-full items-center justify-between text-left"
                  onClick={() => setExpanded(isExpanded ? null : role.key)}
                >
                  <div>
                    <div className="font-medium text-[var(--fg-default)]">{role.name}</div>
                    <div className="text-xs text-[var(--fg-subtle)]">{role.key}</div>
                  </div>
                  <Badge variant="secondary">
                    {role.permissions.length} permission{role.permissions.length === 1 ? "" : "s"}
                  </Badge>
                </button>
                {isExpanded && (
                  <div className="mt-3 flex flex-wrap gap-1.5 border-t border-[var(--border-default)] pt-3">
                    {role.permissions.length === 0 && (
                      <span className="text-xs text-[var(--fg-subtle)]">
                        No permissions granted (deliberate — e.g. Read Only).
                      </span>
                    )}
                    {role.permissions.map((permission) => (
                      <span
                        key={permission}
                        className="rounded bg-[var(--gray-100)] px-2 py-0.5 font-mono text-xs text-[var(--fg-muted)]"
                      >
                        {permission}
                      </span>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
