"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download } from "lucide-react";

import { DataTable, type DataTableColumn } from "@/components/data-table";
import { FormSection } from "@/components/form-section";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { ApiError, apiFetch } from "@/lib/api";
import { REPORT_FORMATS, type Report, type ReportType } from "@/lib/types";

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
      <CardContent className="pt-5">
        <FormSection title="Generate a report" className="mb-0">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-[var(--fg-subtle)]" htmlFor="report-type">
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
              <label className="text-xs text-[var(--fg-subtle)]" htmlFor="report-format">
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
            <Button size="sm" disabled={!reportType || generate.isPending} onClick={() => generate.mutate()}>
              {generate.isPending ? "Generating…" : "Generate"}
            </Button>
          </div>
          {generate.isError && (
            <p className="mt-2 text-sm text-[var(--critical-600)]">
              {generate.error instanceof ApiError ? generate.error.message : "Could not generate report."}
            </p>
          )}
        </FormSection>
      </CardContent>
    </Card>
  );
}

export default function ReportsPage() {
  const { data: reports, isLoading, error, refetch } = useQuery<Report[]>({
    queryKey: ["reports"],
    queryFn: () => apiFetch<Report[]>("/api/v1/reports"),
  });

  const download = useMutation({
    mutationFn: (reportId: string) =>
      apiFetch<{ download_url: string }>(`/api/v1/reports/${reportId}/download`),
    onSuccess: (data) => {
      window.location.href = data.download_url;
    },
  });

  const columns: DataTableColumn<Report>[] = [
    {
      key: "report_type",
      header: "Report",
      render: (report) => (
        <span className="font-medium capitalize">{report.report_type.replace(/_/g, " ")}</span>
      ),
      sortValue: (report) => report.report_type,
    },
    {
      key: "format",
      header: "Format",
      render: (report) => report.format.toUpperCase(),
    },
    {
      key: "status",
      header: "Status",
      render: (report) => (
        <div className="flex flex-col gap-0.5">
          <StatusBadge status={report.status} />
          {report.status === "failed" && report.error_message && (
            <span className="text-xs text-[var(--critical-600)]">{report.error_message}</span>
          )}
        </div>
      ),
      sortValue: (report) => report.status,
    },
    {
      key: "created_at",
      header: "Generated",
      render: (report) => new Date(report.created_at).toLocaleString(),
      sortValue: (report) => report.created_at,
    },
  ];

  return (
    <div>
      <PageHeader
        title="Reports"
        description="Export your organization's own compliance, security, sales, and support data as PDF, DOCX, XLSX, or CSV. Every download is a short-lived signed link."
      />

      <GenerateReportForm />

      <DataTable
        columns={columns}
        data={reports}
        getRowId={(report) => report.id}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
        emptyTitle="No reports generated yet"
        rowActions={(report) =>
          report.status === "completed" ? (
            <Button
              size="sm"
              variant="outline"
              disabled={download.isPending}
              onClick={() => download.mutate(report.id)}
            >
              <Download className="h-3.5 w-3.5" aria-hidden="true" />
              Download
            </Button>
          ) : undefined
        }
      />
    </div>
  );
}
