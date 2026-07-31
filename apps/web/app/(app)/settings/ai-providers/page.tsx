"use client";

import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { AIProviderStatus } from "@/lib/types";

export default function AIProvidersSettingsPage() {
  const { data: providers, isLoading, error } = useQuery<AIProviderStatus[]>({
    queryKey: ["ai", "providers"],
    queryFn: () => apiFetch<AIProviderStatus[]>("/api/v1/ai/providers"),
  });

  const activeProvider = providers?.find((p) => p.active);

  return (
    <div>
      <PageHeader
        title="AI Providers"
        description="spec §57 Model Gateway. No API key is ever stored in the database for any provider —
          every one is set via environment variable only, the same convention every OAuth
          integration in this build follows. This page shows live status, not a place to paste
          a key."
      />

      {isLoading && <p className="text-sm text-neutral-500">Loading…</p>}
      {error && <p className="text-sm text-red-600">Could not load provider status.</p>}

      {providers && !activeProvider && (
        <Card className="mb-4">
          <CardContent className="pt-6">
            <p className="text-sm text-amber-700">
              No real provider is currently active — the AI Gateway is running in demo mode
              (`DemoAdapter`). Set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` and `AI_PROVIDER` to
              activate a real one.
            </p>
          </CardContent>
        </Card>
      )}

      <div className="flex flex-col gap-2">
        {providers?.map((provider) => (
          <Card key={provider.provider_key}>
            <CardContent className="flex items-center justify-between pt-6">
              <div>
                <div className="font-medium text-neutral-900">{provider.name}</div>
                <div className="text-xs text-neutral-400">
                  {provider.has_adapter
                    ? `Set ${provider.provider_key.toUpperCase()}_API_KEY to configure`
                    : "No adapter built yet for this provider"}
                </div>
              </div>
              <div className="flex gap-2">
                {provider.active && <Badge variant="success">Active</Badge>}
                {!provider.active && provider.configured && (
                  <Badge variant="outline">Configured, not active</Badge>
                )}
                {!provider.configured && provider.has_adapter && (
                  <Badge variant="outline">Not configured</Badge>
                )}
                {!provider.has_adapter && <Badge variant="secondary">Not built</Badge>}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
