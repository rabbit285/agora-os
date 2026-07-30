"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api";
import { useCurrentOrganization } from "@/lib/session";
import type { LegalEntity, Organization, Team } from "@/lib/types";

function LegalEntitiesSection() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [country, setCountry] = useState("");

  const { data: entities } = useQuery<LegalEntity[]>({
    queryKey: ["organizations", "current", "legal-entities"],
    queryFn: () => apiFetch<LegalEntity[]>("/api/v1/organizations/current/legal-entities"),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["organizations", "current", "legal-entities"] });

  const create = useMutation({
    mutationFn: () =>
      apiFetch<LegalEntity>("/api/v1/organizations/current/legal-entities", {
        method: "POST",
        body: { name, country: country.trim() ? country.trim().toUpperCase() : null },
      }),
    onSuccess: () => {
      setName("");
      setCountry("");
      invalidate();
    },
  });

  const makeDefault = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/api/v1/organizations/current/legal-entities/${id}`, {
        method: "PATCH",
        body: { is_default: true },
      }),
    onSuccess: invalidate,
  });

  const archive = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/api/v1/organizations/current/legal-entities/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });

  const activeEntities = entities?.filter((e) => e.is_active) ?? [];

  return (
    <Card className="max-w-2xl">
      <CardContent className="flex flex-col gap-4 pt-6">
        <div>
          <h2 className="text-sm font-semibold text-neutral-900">Legal Entities</h2>
          <p className="text-xs text-neutral-500">
            spec §53 multi-tenancy — every organization has one default entity; parent-org/
            subsidiary hierarchy is not yet built (see docs/KNOWN_LIMITATIONS.md).
          </p>
        </div>

        <div className="flex flex-col gap-2">
          {activeEntities.map((entity) => (
            <div
              key={entity.id}
              className="flex items-center justify-between rounded border border-neutral-200 px-3 py-2 text-sm"
            >
              <div className="flex items-center gap-2">
                <span className="font-medium text-neutral-900">{entity.name}</span>
                {entity.country && (
                  <span className="text-xs text-neutral-400">{entity.country}</span>
                )}
                {entity.is_default && <Badge variant="outline">Default</Badge>}
              </div>
              <div className="flex items-center gap-2">
                {!entity.is_default && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={makeDefault.isPending}
                    onClick={() => makeDefault.mutate(entity.id)}
                  >
                    Make default
                  </Button>
                )}
                {!entity.is_default && (
                  <Button
                    size="sm"
                    variant="destructive"
                    disabled={archive.isPending}
                    onClick={() => archive.mutate(entity.id)}
                  >
                    Archive
                  </Button>
                )}
              </div>
            </div>
          ))}
          {activeEntities.length === 0 && (
            <p className="text-sm text-neutral-500">No legal entities yet.</p>
          )}
        </div>

        <div className="flex gap-2">
          <Input
            placeholder="Entity name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Input
            placeholder="Country (ISO 2-letter, optional)"
            value={country}
            maxLength={2}
            onChange={(e) => setCountry(e.target.value)}
            className="w-56"
          />
          <Button disabled={!name.trim() || create.isPending} onClick={() => create.mutate()}>
            Add
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function TeamsSection({ entities }: { entities: LegalEntity[] | undefined }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [legalEntityId, setLegalEntityId] = useState("");

  const { data: teams } = useQuery<Team[]>({
    queryKey: ["organizations", "current", "teams"],
    queryFn: () => apiFetch<Team[]>("/api/v1/organizations/current/teams"),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["organizations", "current", "teams"] });

  const create = useMutation({
    mutationFn: () =>
      apiFetch<Team>("/api/v1/organizations/current/teams", {
        method: "POST",
        body: { name, legal_entity_id: legalEntityId || null },
      }),
    onSuccess: () => {
      setName("");
      setLegalEntityId("");
      invalidate();
    },
  });

  const archive = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/api/v1/organizations/current/teams/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });

  const activeTeams = teams?.filter((t) => t.is_active) ?? [];
  const entityName = (id: string | null) => entities?.find((e) => e.id === id)?.name ?? null;

  return (
    <Card className="max-w-2xl">
      <CardContent className="flex flex-col gap-4 pt-6">
        <h2 className="text-sm font-semibold text-neutral-900">Teams</h2>

        <div className="flex flex-col gap-2">
          {activeTeams.map((team) => (
            <div
              key={team.id}
              className="flex items-center justify-between rounded border border-neutral-200 px-3 py-2 text-sm"
            >
              <div className="flex items-center gap-2">
                <span className="font-medium text-neutral-900">{team.name}</span>
                {entityName(team.legal_entity_id) && (
                  <span className="text-xs text-neutral-400">
                    {entityName(team.legal_entity_id)}
                  </span>
                )}
              </div>
              <Button
                size="sm"
                variant="destructive"
                disabled={archive.isPending}
                onClick={() => archive.mutate(team.id)}
              >
                Archive
              </Button>
            </div>
          ))}
          {activeTeams.length === 0 && <p className="text-sm text-neutral-500">No teams yet.</p>}
        </div>

        <div className="flex gap-2">
          <Input placeholder="Team name" value={name} onChange={(e) => setName(e.target.value)} />
          <select
            className="flex h-9 rounded-md border border-neutral-300 bg-white px-3 py-1 text-sm shadow-sm"
            value={legalEntityId}
            onChange={(e) => setLegalEntityId(e.target.value)}
          >
            <option value="">No legal entity</option>
            {entities?.map((entity) => (
              <option key={entity.id} value={entity.id}>
                {entity.name}
              </option>
            ))}
          </select>
          <Button disabled={!name.trim() || create.isPending} onClick={() => create.mutate()}>
            Add
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

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

  const { data: entities, error: entitiesError } = useQuery<LegalEntity[]>({
    queryKey: ["organizations", "current", "legal-entities"],
    queryFn: () => apiFetch<LegalEntity[]>("/api/v1/organizations/current/legal-entities"),
  });

  return (
    <div className="flex flex-col gap-6">
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

      {entitiesError ? (
        <p className="text-sm text-red-600">
          Could not load legal entities and teams (requires the org.entities.manage permission).
        </p>
      ) : (
        <>
          <LegalEntitiesSection />
          <TeamsSection entities={entities} />
        </>
      )}
    </div>
  );
}
