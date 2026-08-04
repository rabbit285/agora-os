"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { ApiError, apiFetch } from "@/lib/api";
import { REPORT_FORMATS, type Report, type ReportType } from "@/lib/types";

const STATUS_VARIANT: Record<string, "default" | "outline"> = {
  completed: "default",
  failed: "outline",
  generating: "outline",
};

function GenerateReportForm() {
  const queryClient = useQueryClient();
  const { data: reportTypes } = useQuery<ReportType[]>({
    queryKey: ["reports", "types"],
    queryFn: () => apiFetch<ReportType[]>("/api/v1/reports/types"),
  });

  const [reportType, setReportType] = useState("");
  const [format, setFormat] = useState<string>(REPORT_FORMATS[0]);

  const generate = useMutation({
    mutationFn: () =>
      apiFetch<Report>("/api/v1/reports", {
        method: "POST",
        body: { report_type: reportType, format },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["reports"] }),
  });

  return (
    <Card className="mb-6 max-w-2xl">
      <CardContent className="flex flex-col gap-3 pt-6">
        <h2 className="text-sm font-semibold text-neutral-900">Generate a report</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-neutral-500" htmlFor="report-type">
              Report
            </label>
            <Select
              id="report-type"
              value={reportType}
              onChange={(e) => setReportType(e.target.value)}
              className="w-64"
            >
              <option value="">Select a report…</option>
              {reportTypes?.map((rt) => (
                <option key={rt.key} value={rt.key}>
                  {rt.label}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-neutral-500" htmlFor="report-format">
              Format
            </label>
            <Select
              id="report-format"
              value={format}
              onChange={(e) => setFormat(e.target.value)}
              className="w-28"
            >
              {REPORT_FORMATS.map((f) => (
                <option key={f} value={f}>
                  {f.toUpperCase()}
                </option>
              ))}
            </Select>
          </div>
          <Button
            size="sm"
            disabled={!reportType || generate.isPending}
            onClick={() => generate.mutate()}
          >
            {generate.isPending ? "Generating…" : "Generate"}
          </Button>
        </div>
        {generate.isError && (
          <p className="text-sm text-red-600">
            {generate.error instanceof ApiError ? generate.error.message : "Could not generate report."}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function ReportRow({ report }: { report: Report }) {
  const download = useMutation({
    mutationFn: () =>
      apiFetch<{ download_url: string }>(`/api/v1/reports/${report.id}/download`),
    onSuccess: (data) => {
      window.location.href = data.download_url;
    },
  });

  return (
    <Card>
      <CardContent className="flex items-center justify-between pt-6">
        <div>
          <div className="font-medium text-neutral-900">
            {report.report_type.replace(/_/g, " ")} · {report.format.toUpperCase()}
          </div>
          <div className="mt-1 flex items-center gap-2 text-xs text-neutral-400">
            <Badge variant={STATUS_VARIANT[report.status] ?? "outline"}>{report.status}</Badge>
            <span>{new Date(report.created_at).toLocaleString()}</span>
          </div>
          {report.status === "failed" && report.error_message && (
            <p className="mt-1 text-xs text-red-600">{report.error_message}</p>
          )}
        </div>
        {report.status === "completed" && (
          <Button size="sm" variant="outline" disabled={download.isPending} onClick={() => download.mutate()}>
            {download.isPending ? "Getting link…" : "Download"}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

export default function ReportsPage() {
  const { data: reports, isLoading } = useQuery<Report[]>({
    queryKey: ["reports"],
    queryFn: () => apiFetch<Report[]>("/api/v1/reports"),
  });

  return (
    <div>
      <PageHeader
        title="Reports"
        description="spec §65 — 14 report types, each built from this org's own real data. Exported
          as PDF, DOCX, XLSX, or CSV; every download is a short-lived signed link (the same
          mechanism spec §65 calls a Secure link), not an emailed or permanently public file."
      />

      <GenerateReportForm />

      {isLoading && <p className="text-sm text-neutral-500">Loading…</p>}
      {reports && reports.length === 0 && (
        <p className="text-sm text-neutral-500">No reports generated yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {reports?.map((report) => (
          <ReportRow key={report.id} report={report} />
        ))}
      </div>
    </div>
  );
}
