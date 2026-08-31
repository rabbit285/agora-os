"use client";

import { useQuery } from "@tanstack/react-query";
import { Clock, Radio } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { ConnectorCatalog, EvidenceEvent } from "@/lib/types";

/** Monitoring sources, each reporting its real state.
 *
 * Nothing on this page may look connected that is not. A customer who
 * believes their GitHub settings are being watched, and is wrong, is
 * worse off than one who knows they are not — they will stop checking.
 *
 * So there is no "Connect" button on a connector that cannot yet produce
 * evidence, and the observation feed stays genuinely empty rather than
 * being seeded with examples.
 */
export default function IntegrationsPage() {
  const { data: catalog } = useQuery<ConnectorCatalog>({
    queryKey: ["compliance", "connectors"],
    queryFn: () => apiFetch<ConnectorCatalog>("/api/v1/compliance/connectors"),
  });

  const { data: events } = useQuery<EvidenceEvent[]>({
    queryKey: ["compliance", "evidence-events"],
    queryFn: () => apiFetch<EvidenceEvent[]>("/api/v1/compliance/evidence-events"),
  });

  const byCategory = (catalog?.connectors ?? []).reduce<
    Record<string, ConnectorCatalog["connectors"]>
  >((groups, connector) => {
    (groups[connector.category] ??= []).push(connector);
    return groups;
  }, {});

  return (
    <div>
      <PageHeader
        title="Integrations"
        description="Where Veyntra will watch your compliance position between audits."
      />

      <Card className="mb-6">
        <CardContent className="pt-6">
          <p className="text-sm leading-relaxed text-[var(--fg-muted)]">
            Compliance decays. A control that passed in March fails in June because someone
            turned off branch protection, and nobody finds out until the next audit. Connected
            sources will report changes as they happen, and the affected control is marked for
            reassessment.
          </p>
          {catalog && catalog.available_count === 0 && (
            <p className="mt-3 text-sm leading-relaxed text-[var(--fg-default)]">
              <strong>None of these are connected yet.</strong> The receiving side is built
              and every source below is listed with what it would observe, but nothing is
              sending data, so nothing here is monitoring your systems today.
            </p>
          )}
        </CardContent>
      </Card>

      <div className="flex flex-col gap-6">
        {Object.entries(byCategory).map(([category, connectors]) => (
          <section key={category}>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
              {category}
            </h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {connectors.map((connector) => (
                <Card key={connector.key}>
                  <CardContent className="pt-6">
                    <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                      <span className="font-medium text-[var(--fg-default)]">
                        {connector.name}
                      </span>
                      {/* No Connect button on something that cannot yet
                          produce evidence. A control that does nothing is
                          worse than an absent one. */}
                      <Badge variant="secondary" className="gap-1">
                        <Clock className="h-3 w-3" aria-hidden="true" />
                        {connector.status === "available" ? "Connected" : "Coming soon"}
                      </Badge>
                    </div>
                    <p className="text-sm leading-relaxed text-[var(--fg-muted)]">
                      {connector.observes}
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </section>
        ))}
      </div>

      <section className="mt-8">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Observations
        </h2>
        <Card>
          <CardContent className="pt-6">
            {events && events.length > 0 ? (
              <ul className="flex flex-col gap-3">
                {events.map((event) => (
                  <li key={event.id} className="flex items-start gap-2.5">
                    <Radio
                      className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--brand-primary)]"
                      aria-hidden="true"
                    />
                    <div>
                      <p className="text-sm text-[var(--fg-default)]">{event.summary}</p>
                      <p className="mt-0.5 text-xs text-[var(--fg-subtle)]">
                        {event.source} · {new Date(event.observed_at).toLocaleString()}
                        {event.triggered_reassessment
                          ? " · marked a control for reassessment"
                          : ""}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-[var(--fg-muted)]">
                No observations recorded. This stays empty until a source is genuinely
                connected — it is never filled with examples.
              </p>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
