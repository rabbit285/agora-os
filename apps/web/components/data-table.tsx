"use client";

import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { LoadingSkeleton } from "@/components/loading-skeleton";
import { PermissionDenied } from "@/components/permission-denied";
import { cn } from "@/lib/utils";

export type DataTableColumn<T> = {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
  /** Value used for client-side sorting when this column's header is clicked. */
  sortValue?: (row: T) => string | number | null | undefined;
  className?: string;
  align?: "left" | "right" | "center";
};

/** One shared enterprise table pattern — sort, row click-through, density,
 * and the 4 required non-happy-path states in one place instead of each
 * list page hand-rolling its own <div> of Cards. */
export function DataTable<T>({
  columns,
  data,
  getRowId,
  onRowClick,
  isLoading,
  error,
  onRetry,
  permissionDenied,
  emptyTitle = "Nothing here yet",
  emptyDescription,
  density = "comfortable",
  rowActions,
  className,
}: {
  columns: DataTableColumn<T>[];
  data: T[] | undefined;
  getRowId: (row: T) => string;
  onRowClick?: (row: T) => void;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  permissionDenied?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  density?: "comfortable" | "compact";
  rowActions?: (row: T) => React.ReactNode;
  className?: string;
}) {
  const [sort, setSort] = useState<{ key: string; direction: "asc" | "desc" } | null>(null);

  const sorted = useMemo(() => {
    if (!data) return data;
    if (!sort) return data;
    const column = columns.find((c) => c.key === sort.key);
    if (!column?.sortValue) return data;
    const withValues = data.map((row) => ({ row, value: column.sortValue!(row) }));
    withValues.sort((a, b) => {
      if (a.value == null && b.value == null) return 0;
      if (a.value == null) return 1;
      if (b.value == null) return -1;
      const cmp = a.value < b.value ? -1 : a.value > b.value ? 1 : 0;
      return sort.direction === "asc" ? cmp : -cmp;
    });
    return withValues.map((w) => w.row);
  }, [data, sort, columns]);

  function toggleSort(key: string) {
    setSort((current) => {
      if (current?.key !== key) return { key, direction: "asc" };
      if (current.direction === "asc") return { key, direction: "desc" };
      return null;
    });
  }

  const rowHeight = density === "compact" ? "h-9" : "h-11";
  const cellPad = density === "compact" ? "px-3 py-1.5" : "px-3 py-2.5";

  if (permissionDenied) return <PermissionDenied />;
  if (error) return <ErrorState onRetry={onRetry} description={error instanceof Error ? error.message : undefined} />;
  if (isLoading) return <LoadingSkeleton rows={5} className={className} />;
  if (!sorted || sorted.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} className={className} />;
  }

  return (
    <div
      className={cn(
        "overflow-x-auto rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)]",
        className,
      )}
    >
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-[var(--border-default)] bg-[var(--bg-sunken)]">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={cn(
                  "px-3 py-2 text-xs font-medium uppercase tracking-wide text-[var(--fg-muted)]",
                  column.align === "right" && "text-right",
                  column.align === "center" && "text-center",
                  !column.align && "text-left",
                )}
              >
                {column.sortValue ? (
                  <button
                    type="button"
                    onClick={() => toggleSort(column.key)}
                    className="inline-flex items-center gap-1 hover:text-[var(--fg-default)]"
                  >
                    {column.header}
                    {sort?.key === column.key ? (
                      sort.direction === "asc" ? (
                        <ArrowUp className="h-3 w-3" aria-hidden="true" />
                      ) : (
                        <ArrowDown className="h-3 w-3" aria-hidden="true" />
                      )
                    ) : (
                      <ArrowUpDown className="h-3 w-3 opacity-40" aria-hidden="true" />
                    )}
                  </button>
                ) : (
                  column.header
                )}
              </th>
            ))}
            {rowActions && <th scope="col" className="w-10 px-3 py-2" />}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => {
            const id = getRowId(row);
            return (
              <tr
                key={id}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={cn(
                  rowHeight,
                  "border-b border-[var(--border-default)] last:border-b-0",
                  onRowClick &&
                    "cursor-pointer transition-colors duration-[var(--transition-fast)] hover:bg-[var(--bg-surface-hover)]",
                )}
              >
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={cn(
                      cellPad,
                      "text-[var(--fg-default)]",
                      column.align === "right" && "text-right",
                      column.align === "center" && "text-center",
                      column.className,
                    )}
                  >
                    {column.render(row)}
                  </td>
                ))}
                {rowActions && (
                  <td className={cn(cellPad, "text-right")} onClick={(e) => e.stopPropagation()}>
                    {rowActions(row)}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
