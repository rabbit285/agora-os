"use client";

import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { Workflow, WorkflowTemplate } from "@/lib/types";

export default function WorkflowTemplatesPage() {
  const router = useRouter();
  const { data: templates } = useQuery<WorkflowTemplate[]>({
    queryKey: ["automation", "templates"],
    queryFn: () => apiFetch<WorkflowTemplate[]>("/api/v1/automation/templates"),
  });

  const useTemplate = useMutation({
    mutationFn: (templateId: string) =>
      apiFetch<Workflow>(`/api/v1/automation/templates/${templateId}/use`, { method: "POST" }),
    onSuccess: (workflow) => {
      router.push(`/automation/workflows/${workflow.id}`);
    },
  });

  return (
    <div>
      <PageHeader
        title="Workflow Templates"
        description="A starting point, not a locked-in choice — using a template clones it into a new draft workflow you can edit freely (spec §41)."
      />
      {templates?.length === 0 && (
        <p className="text-sm text-neutral-500">No templates available yet.</p>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {templates?.map((template) => (
          <Card key={template.id}>
            <CardContent className="flex flex-col gap-2 pt-6">
              <div className="flex items-center justify-between">
                <div className="font-medium text-neutral-900">{template.name}</div>
                <Badge variant="outline">{template.category}</Badge>
              </div>
              {template.description && (
                <p className="text-sm text-neutral-600">{template.description}</p>
              )}
              <div className="text-xs text-neutral-400">
                {template.steps.length} step(s) · trigger: {template.trigger_type}
              </div>
              <Button
                size="sm"
                disabled={useTemplate.isPending}
                onClick={() => useTemplate.mutate(template.id)}
                className="self-start"
              >
                Use this template
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
