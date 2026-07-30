"use client";

import Link from "next/link";
import { use } from "react";
import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { FrameworkDashboard } from "@/lib/types";

export default function FrameworkDashboardPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  const { data, isLoading, error } = useQuery<FrameworkDashboard>({
    queryKey: ["compliance", "frameworks", id, "dashboard"],
    queryFn: () => apiFetch<FrameworkDashboard>(`/api/v1/compliance/frameworks/${id}/dashboard`),
  });

  if (isLoading) return <p className="text-sm text-neutral-500">Loading…</p>;
  if (error) {
    return (
      <p className="text-sm text-red-600">
        {error instanceof ApiError ? error.message : "Could not load this framework."}
      </p>
    );
  }
  if (!data) return null;

  return (
    <div>
      <PageHeader
        title={data.framework.name}
        description={data.framework.description ?? undefined}
        actions={
          <div className="flex items-center gap-2">
            <span className="text-sm text-neutral-500">Coverage</span>
            <Badge variant={data.coverage_percent === 100 ? "success" : "outline"}>
              {data.coverage_percent}%
            </Badge>
          </div>
        }
      />

      {data.requirements.length === 0 && (
        <p className="text-sm text-neutral-500">This framework has no requirements yet.</p>
      )}

      <div className="flex flex-col gap-3">
        {data.requirements.map((requirement) => (
          <Card key={requirement.id}>
            <CardContent className="pt-6">
              <div className="mb-2 flex items-center justify-between">
                <div>
                  <span className="font-mono text-xs text-neutral-400">
                    {requirement.reference_code}
                  </span>
                  <div className="font-medium text-neutral-900">{requirement.title}</div>
                </div>
                {requirement.controls.length === 0 && (
                  <Badge variant="destructive">No control mapped</Badge>
                )}
              </div>
              {requirement.controls.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {requirement.controls.map((control) => (
                    <Link key={control.id} href={`/compliance/controls/${control.id}`}>
                      <Badge variant="secondary" className="cursor-pointer hover:bg-neutral-300">
                        {control.title}
                      </Badge>
                    </Link>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
