"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import type {
  Risk,
  SecurityAsset,
  SecurityIncidentDetail,
  SecurityIncidentStatus,
  Task,
} from "@/lib/types";

const WORKFLOW: SecurityIncidentStatus[] = [
  "detected",
  "triage",
  "investigation",
  "containment",
  "eradication",
  "recovery",
  "postmortem",
  "closed",
];

function TimelineSection({ id }: { id: string }) {
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const [entryType, setEntryType] = useState<"update" | "communication">("update");

  const { data: incident } = useQuery<SecurityIncidentDetail>({
    queryKey: ["security", "incidents", id],
    queryFn: () => apiFetch<SecurityIncidentDetail>(`/api/v1/security/incidents/${id}`),
  });

  const addEntry = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/security/incidents/${id}/timeline`, {
        method: "POST",
        body: { entry_type: entryType, body },
      }),
    onSuccess: () => {
      setBody("");
      queryClient.invalidateQueries({ queryKey: ["security", "incidents", id] });
    },
  });

  return (
    <div className="mb-6">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        Timeline &amp; Communication
      </h2>
      <Card className="mb-3">
        <CardContent className="flex flex-col gap-2 pt-6">
          <div className="flex gap-2">
            <Button
              size="sm"
              variant={entryType === "update" ? "default" : "outline"}
              onClick={() => setEntryType("update")}
            >
              Update
            </Button>
            <Button
              size="sm"
              variant={entryType === "communication" ? "default" : "outline"}
              onClick={() => setEntryType("communication")}
            >
              Communication
            </Button>
          </div>
          <Textarea
            placeholder="Add a timeline entry…"
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <Button
            size="sm"
            disabled={!body.trim() || addEntry.isPending}
            onClick={() => addEntry.mutate()}
            className="self-start"
          >
            Add entry
          </Button>
        </CardContent>
      </Card>
      {incident?.timeline.length === 0 && (
        <p className="text-sm text-neutral-500">No timeline entries yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {incident?.timeline.map((entry) => (
          <Card key={entry.id}>
            <CardContent className="pt-6">
              <div className="mb-1 flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
                  {entry.entry_type}
                </span>
                <span className="text-xs text-neutral-400">
                  {new Date(entry.created_at).toLocaleString()}
                </span>
              </div>
              <p className="text-sm text-neutral-900">{entry.body}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function AffectedAssetsSection({ id }: { id: string }) {
  const queryClient = useQueryClient();
  const [assetId, setAssetId] = useState("");

  const { data: incident } = useQuery<SecurityIncidentDetail>({
    queryKey: ["security", "incidents", id],
    queryFn: () => apiFetch<SecurityIncidentDetail>(`/api/v1/security/incidents/${id}`),
  });

  const { data: assets } = useQuery<SecurityAsset[]>({
    queryKey: ["security", "assets"],
    queryFn: () => apiFetch<SecurityAsset[]>("/api/v1/security/assets"),
  });

  const linkAsset = useMutation({
    mutationFn: (asset_id: string) =>
      apiFetch(`/api/v1/security/incidents/${id}/assets`, {
        method: "POST",
        body: { asset_id },
      }),
    onSuccess: () => {
      setAssetId("");
      queryClient.invalidateQueries({ queryKey: ["security", "incidents", id] });
    },
  });

  const linkedIds = new Set(incident?.affected_assets.map((a) => a.id));
  const availableAssets = assets?.filter((a) => !linkedIds.has(a.id)) ?? [];

  return (
    <div className="mb-6">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        Affected Assets
      </h2>
      {incident?.affected_assets.length === 0 && (
        <p className="mb-3 text-sm text-neutral-500">No assets linked to this incident yet.</p>
      )}
      <div className="mb-3 flex flex-col gap-2">
        {incident?.affected_assets.map((asset) => (
          <Link key={asset.id} href={`/security/assets/${asset.id}`}>
            <Card className="transition-colors hover:border-neutral-400">
              <CardContent className="flex items-center justify-between pt-6">
                <div className="font-medium text-neutral-900">{asset.name}</div>
                <SeverityBadge severity={asset.criticality} />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
      {availableAssets.length > 0 && (
        <Card>
          <CardContent className="flex items-center gap-2 pt-6">
            <select
              className="h-9 flex-1 rounded-md border border-neutral-300 bg-white px-3 text-sm"
              value={assetId}
              onChange={(e) => setAssetId(e.target.value)}
            >
              <option value="">Select an asset to link…</option>
              {availableAssets.map((asset) => (
                <option key={asset.id} value={asset.id}>
                  {asset.name}
                </option>
              ))}
            </select>
            <Button
              size="sm"
              disabled={!assetId || linkAsset.isPending}
              onClick={() => linkAsset.mutate(assetId)}
            >
              Link
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function PostmortemSection({ id }: { id: string }) {
  const queryClient = useQueryClient();

  const { data: incident } = useQuery<SecurityIncidentDetail>({
    queryKey: ["security", "incidents", id],
    queryFn: () => apiFetch<SecurityIncidentDetail>(`/api/v1/security/incidents/${id}`),
  });

  const [rootCause, setRootCause] = useState(incident?.root_cause ?? "");
  const [lessons, setLessons] = useState(incident?.lessons_learned ?? "");
  const [editing, setEditing] = useState(false);

  const save = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/security/incidents/${id}/postmortem`, {
        method: "PATCH",
        body: { root_cause: rootCause, lessons_learned: lessons },
      }),
    onSuccess: () => {
      setEditing(false);
      queryClient.invalidateQueries({ queryKey: ["security", "incidents", id] });
    },
  });

  if (!incident) return null;

  return (
    <div className="mb-6">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        Root Cause &amp; Lessons Learned
      </h2>
      <Card>
        <CardContent className="flex flex-col gap-3 pt-6">
          {editing ? (
            <>
              <div>
                <label className="mb-1 block text-xs text-neutral-500">Root cause</label>
                <Textarea value={rootCause} onChange={(e) => setRootCause(e.target.value)} />
              </div>
              <div>
                <label className="mb-1 block text-xs text-neutral-500">Lessons learned</label>
                <Textarea value={lessons} onChange={(e) => setLessons(e.target.value)} />
              </div>
              <div className="flex gap-2">
                <Button size="sm" disabled={save.isPending} onClick={() => save.mutate()}>
                  Save
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
                  Cancel
                </Button>
              </div>
            </>
          ) : (
            <>
              <div>
                <div className="text-xs text-neutral-500">Root cause</div>
                <p className="text-sm text-neutral-900">
                  {incident.root_cause || "Not documented yet."}
                </p>
              </div>
              <div>
                <div className="text-xs text-neutral-500">Lessons learned</div>
                <p className="text-sm text-neutral-900">
                  {incident.lessons_learned || "Not documented yet."}
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                className="self-start"
                onClick={() => {
                  setRootCause(incident.root_cause ?? "");
                  setLessons(incident.lessons_learned ?? "");
                  setEditing(true);
                }}
              >
                Edit
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function IncidentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();

  const { data: incident } = useQuery<SecurityIncidentDetail>({
    queryKey: ["security", "incidents", id],
    queryFn: () => apiFetch<SecurityIncidentDetail>(`/api/v1/security/incidents/${id}`),
  });

  const { data: risks } = useQuery<Risk[]>({
    queryKey: ["compliance", "risks"],
    queryFn: () => apiFetch<Risk[]>("/api/v1/compliance/risks"),
    enabled: !!incident?.related_risk_id,
  });

  const { data: tasks } = useQuery<Task[]>({
    queryKey: ["tasks"],
    queryFn: () => apiFetch<Task[]>("/api/v1/tasks"),
    enabled: !!incident?.related_task_id,
  });

  const advanceStatus = useMutation({
    mutationFn: (status: SecurityIncidentStatus) =>
      apiFetch(`/api/v1/security/incidents/${id}`, { method: "PATCH", body: { status } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["security", "incidents", id] });
      queryClient.invalidateQueries({ queryKey: ["security", "overview"] });
    },
  });

  if (!incident) return null;

  const linkedRisk = risks?.find((r) => r.id === incident.related_risk_id);
  const linkedTask = tasks?.find((t) => t.id === incident.related_task_id);
  const currentIndex = WORKFLOW.indexOf(incident.status);
  const nextStatus = WORKFLOW[currentIndex + 1];

  return (
    <div>
      <PageHeader
        title={incident.title}
        description={incident.description ?? undefined}
        actions={<SeverityBadge severity={incident.severity} />}
      />

      <div className="mb-6 flex items-center gap-3">
        <span className="text-sm text-neutral-500">Status:</span>
        <StatusBadge status={incident.status} />
        {nextStatus && (
          <Button
            size="sm"
            variant="outline"
            disabled={advanceStatus.isPending}
            onClick={() => advanceStatus.mutate(nextStatus)}
          >
            Advance to {nextStatus.replace(/_/g, " ")}
          </Button>
        )}
      </div>

      <AffectedAssetsSection id={id} />
      <TimelineSection id={id} />
      <PostmortemSection id={id} />

      {incident.related_risk_id && (
        <Card className="mb-6">
          <CardContent className="pt-6">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
              Linked Compliance Risk
            </h2>
            <p className="text-xs text-neutral-400 mb-2">
              Critical security incidents automatically create a linked risk so GDPR breach
              notification obligations are tracked (spec section 19).
            </p>
            {linkedRisk ? (
              <Link
                href="/compliance"
                className="text-sm text-neutral-700 hover:underline"
              >
                {linkedRisk.title}
              </Link>
            ) : (
              <span className="text-sm text-neutral-400">Loading…</span>
            )}
          </CardContent>
        </Card>
      )}

      {incident.related_task_id && (
        <Card>
          <CardContent className="pt-6">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
              Response Task
            </h2>
            <p className="text-xs text-neutral-400 mb-2">
              Critical incidents automatically create a response task, and notify the incident
              owner directly if one is assigned (spec section 69 — Security Incident chain).
            </p>
            {linkedTask ? (
              <Link href="/tasks" className="text-sm text-neutral-700 hover:underline">
                {linkedTask.title}
              </Link>
            ) : (
              <span className="text-sm text-neutral-400">Loading…</span>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
