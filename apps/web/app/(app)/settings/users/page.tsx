"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { ApiError, apiFetch } from "@/lib/api";
import { SYSTEM_ROLES, type Invitation, type Membership } from "@/lib/types";

export default function UsersSettingsPage() {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [roleKey, setRoleKey] = useState("employee");
  const [formError, setFormError] = useState<string | null>(null);

  const { data: members, isLoading: membersLoading } = useQuery<Membership[]>({
    queryKey: ["organizations", "current", "members"],
    queryFn: () => apiFetch<Membership[]>("/api/v1/organizations/current/members"),
  });

  const {
    data: invitations,
    isLoading: invitationsLoading,
    error: invitationsError,
  } = useQuery<Invitation[]>({
    queryKey: ["organizations", "current", "invitations"],
    queryFn: () => apiFetch<Invitation[]>("/api/v1/organizations/current/invitations"),
  });

  const createInvitation = useMutation({
    mutationFn: () =>
      apiFetch<Invitation>("/api/v1/organizations/current/invitations", {
        method: "POST",
        body: { email, role_key: roleKey },
      }),
    onSuccess: () => {
      setEmail("");
      setFormError(null);
      queryClient.invalidateQueries({ queryKey: ["organizations", "current", "invitations"] });
    },
    onError: (error) => {
      setFormError(error instanceof ApiError ? error.message : "Something went wrong");
    },
  });

  const revokeInvitation = useMutation({
    mutationFn: (id: string) =>
      apiFetch<Invitation>(`/api/v1/organizations/current/invitations/${id}/revoke`, {
        method: "POST",
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["organizations", "current", "invitations"] }),
  });

  const pendingInvitations = invitations?.filter(
    (invitation) => invitation.accepted_at === null,
  );

  return (
    <div>
      <PageHeader
        title="Users"
        description="Members of this organization and their roles (spec section 54)."
      />

      <Card className="mb-6">
        <CardContent className="flex flex-col gap-3 pt-6">
          <div className="text-sm font-medium text-[var(--fg-default)]">Invite a member</div>
          <div className="flex flex-wrap gap-2">
            <Input
              type="email"
              placeholder="email@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="max-w-xs"
            />
            <Select value={roleKey} onChange={(e) => setRoleKey(e.target.value)} className="max-w-xs">
              {SYSTEM_ROLES.map((role) => (
                <option key={role.key} value={role.key}>
                  {role.name}
                </option>
              ))}
            </Select>
            <Button
              disabled={!email.trim() || createInvitation.isPending}
              onClick={() => createInvitation.mutate()}
            >
              {createInvitation.isPending ? "Sending…" : "Send invite"}
            </Button>
          </div>
          {formError && <p className="text-sm text-[var(--critical-600)]">{formError}</p>}
          <p className="text-xs text-[var(--fg-subtle)]">
            No email provider is configured in this environment — the invitation link is logged
            server-side instead of emailed (see docs/KNOWN_LIMITATIONS.md).
          </p>
        </CardContent>
      </Card>

      {invitationsLoading && <p className="text-sm text-[var(--fg-muted)]">Loading invitations…</p>}
      {invitationsError && (
        <p className="mb-4 text-sm text-[var(--critical-600)]">Could not load pending invitations.</p>
      )}
      {pendingInvitations && pendingInvitations.length > 0 && (
        <div className="mb-6 flex flex-col gap-2">
          <div className="text-sm font-medium text-[var(--fg-default)]">Pending invitations</div>
          {pendingInvitations.map((invitation) => (
            <Card key={invitation.id}>
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="text-sm text-[var(--fg-default)]">{invitation.email}</div>
                  <div className="text-xs text-[var(--fg-subtle)]">
                    {invitation.role_key.replace(/_/g, " ")}
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={revokeInvitation.isPending}
                  onClick={() => revokeInvitation.mutate(invitation.id)}
                >
                  Revoke
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {membersLoading && <p className="text-sm text-[var(--fg-muted)]">Loading…</p>}
      {members && members.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">No members yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {members?.map((member) => (
          <Card key={member.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div className="font-mono text-xs text-[var(--fg-muted)]">{member.user_id}</div>
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
