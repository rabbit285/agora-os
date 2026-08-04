"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { ApiError, apiFetch } from "@/lib/api";
import type { GraphResult } from "@/lib/types";

export function GraphExplorer({
  initialEntityType,
  initialEntityId,
}: {
  initialEntityType: string | null;
  initialEntityId: string | null;
}) {
  const router = useRouter();
  const [entityType, setEntityType] = useState(initialEntityType ?? "");
  const [entityId, setEntityId] = useState(initialEntityId ?? "");
  const [activeType, setActiveType] = useState(initialEntityType);
  const [activeId, setActiveId] = useState(initialEntityId);

  const { data: entityTypes } = useQuery<{ entity_types: string[] }>({
    queryKey: ["knowledge", "graph", "entity-types"],
    queryFn: () => apiFetch<{ entity_types: string[] }>("/api/v1/knowledge/graph/entity-types"),
  });

  const {
    data: graph,
    isLoading,
    error,
  } = useQuery<GraphResult>({
    queryKey: ["knowledge", "graph", activeType, activeId],
    queryFn: () => apiFetch<GraphResult>(`/api/v1/knowledge/graph/${activeType}/${activeId}`),
    enabled: Boolean(activeType && activeId),
  });

  function navigateTo(type: string, id: string) {
    setEntityType(type);
    setEntityId(id);
    setActiveType(type);
    setActiveId(id);
    router.replace(`/knowledge/graph?type=${type}&id=${id}`);
  }

  const groupedEdges = new Map<string, GraphResult["edges"]>();
  for (const edge of graph?.edges ?? []) {
    const list = groupedEdges.get(edge.relation) ?? [];
    list.push(edge);
    groupedEdges.set(edge.relation, list);
  }

  return (
    <div>
      <PageHeader
        title="Knowledge Graph"
        description="Explore how records across every module connect to each other (spec section 10)."
      />

      <Card className="mb-6">
        <CardContent className="flex flex-wrap items-end gap-2 pt-6">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs text-[var(--fg-muted)]">Entity type</label>
            <Select
              value={entityType}
              onChange={(e) => setEntityType(e.target.value)}
              className="w-56"
            >
              <option value="">Select a type…</option>
              {entityTypes?.entity_types.map((t) => (
                <option key={t} value={t}>
                  {t.replace(/_/g, " ")}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-xs text-[var(--fg-muted)]">Entity ID</label>
            <Input
              value={entityId}
              onChange={(e) => setEntityId(e.target.value)}
              placeholder="UUID"
              className="w-72"
            />
          </div>
          <Button
            disabled={!entityType || !entityId.trim()}
            onClick={() => navigateTo(entityType, entityId.trim())}
          >
            Load
          </Button>
        </CardContent>
      </Card>

      {!activeType || !activeId ? (
        <p className="text-sm text-[var(--fg-muted)]">
          Pick an entity type and paste an ID (e.g. from a record&apos;s detail page URL) to see
          its connections.
        </p>
      ) : isLoading ? (
        <p className="text-sm text-[var(--fg-muted)]">Loading…</p>
      ) : error ? (
        <p className="text-sm text-[var(--critical-600)]">
          {error instanceof ApiError ? error.message : "Could not load this entity."}
        </p>
      ) : graph ? (
        <div className="flex flex-col gap-6">
          <Card>
            <CardContent className="pt-6">
              <Badge variant="secondary">{graph.node.entity_type.replace(/_/g, " ")}</Badge>
              <div className="mt-2 text-lg font-medium text-[var(--fg-default)]">{graph.node.label}</div>
              <div className="mt-1 font-mono text-xs text-[var(--fg-subtle)]">{graph.node.id}</div>
            </CardContent>
          </Card>

          {groupedEdges.size === 0 ? (
            <p className="text-sm text-[var(--fg-muted)]">No connected records found.</p>
          ) : (
            Array.from(groupedEdges.entries()).map(([relation, edges]) => (
              <div key={relation}>
                <div className="mb-2 text-sm font-medium text-[var(--fg-default)]">
                  {relation.replace(/_/g, " ")}
                </div>
                <div className="flex flex-col gap-2">
                  {edges.map((edge) => (
                    <Card
                      key={edge.node.id}
                      className="cursor-pointer hover:bg-[var(--bg-surface-hover)]"
                      onClick={() => navigateTo(edge.node.entity_type, edge.node.id)}
                    >
                      <CardContent className="flex items-center justify-between pt-6">
                        <div>
                          <div className="text-sm text-[var(--fg-default)]">{edge.node.label}</div>
                          <div className="text-xs text-[var(--fg-subtle)]">
                            {edge.node.entity_type.replace(/_/g, " ")}
                          </div>
                        </div>
                        <span className="text-xs text-[var(--fg-subtle)]">View →</span>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
}
