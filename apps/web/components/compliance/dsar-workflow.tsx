"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Download, Lock, Search, ShieldAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { API_URL, ApiError, apiFetch } from "@/lib/api";
import type { DSAR, DsarDiscovery } from "@/lib/types";

/** Verification, discovery, and export for one access request.
 *
 * The export control is disabled until the requester is verified, and
 * says why. That is a courtesy, not the enforcement — the API refuses
 * regardless (see app/compliance/dsar.py). A disabled button is a hint;
 * the server is the control, because anything a browser can be persuaded
 * not to render, a browser can also be persuaded to render.
 */
export function DsarWorkflow({ dsar }: { dsar: DSAR }) {
  const queryClient = useQueryClient();
  const [method, setMethod] = useState("");
  const [discovery, setDiscovery] = useState<DsarDiscovery | null>(
    (dsar.discovery_findings as DsarDiscovery | null) ?? null,
  );

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["compliance", "dsars", dsar.id] });

  const verify = useMutation({
    mutationFn: (verified: boolean) =>
      apiFetch<DSAR>(`/api/v1/compliance/dsars/${dsar.id}/verify-identity`, {
        method: "POST",
        body: { verified, method: method || "Not recorded" },
      }),
    onSuccess: invalidate,
  });

  const discover = useMutation({
    mutationFn: () =>
      apiFetch<DsarDiscovery>(`/api/v1/compliance/dsars/${dsar.id}/discover`, { method: "POST" }),
    onSuccess: (data) => {
      setDiscovery(data);
      invalidate();
    },
  });

  const isVerified = dsar.verification_status === "verified";
  const error = verify.error ?? discover.error;

  return (
    <>
      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-medium text-[var(--fg-default)]">Identity verification</h2>
            <Badge
              variant={
                isVerified
                  ? "success"
                  : dsar.verification_status === "failed"
                    ? "destructive"
                    : "secondary"
              }
            >
              {dsar.verification_status}
            </Badge>
          </div>

          <p className="mb-4 text-sm leading-relaxed text-[var(--fg-muted)]">
            Answering an access request means handing over everything held about a named person.
            Until the requester&rsquo;s identity is established, fulfilling it risks disclosing
            personal data to whoever asked rather than to the data subject.
          </p>

          {isVerified ? (
            <p className="flex items-center gap-2 text-sm text-[var(--fg-muted)]">
              <CheckCircle2
                className="h-4 w-4 shrink-0 text-[var(--success-600)]"
                aria-hidden="true"
              />
              Verified{dsar.verification_method ? ` via ${dsar.verification_method}` : ""}
              {dsar.verified_at && ` on ${new Date(dsar.verified_at).toLocaleDateString()}`}
            </p>
          ) : (
            <div className="flex flex-col gap-3">
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-[var(--fg-default)]">How was identity established?</span>
                <Input
                  value={method}
                  placeholder="e.g. Email verification to the address on file"
                  onChange={(e) => setMethod(e.target.value)}
                />
              </label>
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  disabled={verify.isPending || !method.trim()}
                  onClick={() => verify.mutate(true)}
                >
                  Mark verified
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={verify.isPending || !method.trim()}
                  onClick={() => verify.mutate(false)}
                >
                  Record failed verification
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-medium text-[var(--fg-default)]">Data discovery</h2>
            <Button
              size="sm"
              variant="outline"
              disabled={discover.isPending}
              onClick={() => discover.mutate()}
            >
              <Search className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
              {discover.isPending ? "Searching…" : discovery ? "Search again" : "Search data sources"}
            </Button>
          </div>

          {discovery ? (
            <>
              <table className="w-full text-sm">
                <tbody>
                  {discovery.sources.map((source) => (
                    <tr key={source.source} className="border-b border-[var(--border-default)]">
                      <td className="py-1.5 text-[var(--fg-muted)]">{source.source}</td>
                      <td className="py-1.5 text-right font-mono text-[var(--fg-default)]">
                        {source.matches}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-3 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-app)] p-3 text-xs leading-relaxed text-[var(--fg-muted)]">
                {discovery.coverage_note}
              </p>
            </>
          ) : (
            <p className="text-sm text-[var(--fg-muted)]">
              No search has been run for this request yet.
            </p>
          )}
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardContent className="pt-6">
          <h2 className="mb-3 font-medium text-[var(--fg-default)]">Response package</h2>

          {isVerified ? (
            <>
              <p className="mb-3 text-sm text-[var(--fg-muted)]">
                The package records what was searched, what was found, and how identity was
                established, so it still explains itself once separated from Veyntra.
              </p>
              <Button size="sm" asChild>
                {/* A plain link rather than a fetch: the response is a file
                    download, and routing it through JavaScript would mean
                    holding the data subject's package in browser memory for
                    no benefit. */}
                <a
                  href={`${API_URL}/api/v1/compliance/dsars/${dsar.id}/export`}
                  rel="noopener"
                  download
                >
                  <Download className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                  Generate export
                </a>
              </Button>
            </>
          ) : (
            <div className="flex items-start gap-2 rounded-[var(--radius-md)] border border-[var(--warning-500)]/35 bg-[var(--warning-50)] p-3">
              <Lock className="mt-0.5 h-4 w-4 shrink-0 text-[var(--warning-700)]" aria-hidden="true" />
              <div>
                <p className="text-sm font-medium text-[var(--warning-700)]">
                  Export is blocked until identity is verified
                </p>
                <p className="mt-1 text-sm leading-relaxed text-[var(--warning-700)]">
                  This is enforced by the API, not just hidden here — the request is refused
                  server-side whatever the browser does.
                </p>
              </div>
            </div>
          )}

          {dsar.export_generated_at && (
            <p className="mt-3 text-xs text-[var(--fg-subtle)]">
              Last generated {new Date(dsar.export_generated_at).toLocaleString()}
            </p>
          )}
        </CardContent>
      </Card>

      {error && (
        <p className="mb-4 flex items-center gap-2 text-sm text-[var(--critical-600)]">
          <ShieldAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
          {error instanceof ApiError ? error.message : "Something went wrong."}
        </p>
      )}
    </>
  );
}
