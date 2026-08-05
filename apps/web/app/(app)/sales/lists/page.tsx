"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { DataTable, type DataTableColumn } from "@/components/data-table";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import type { SalesListOut } from "@/lib/types";

export default function SalesListsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [listType, setListType] = useState<"company" | "person">("company");

  const { data: lists, isLoading, error, refetch } = useQuery<SalesListOut[]>({
    queryKey: ["sales", "lead-finder", "lists", "all"],
    queryFn: () => apiFetch<SalesListOut[]>("/api/v1/sales/lead-finder/lists"),
  });

  const createList = useMutation({
    mutationFn: () =>
      apiFetch<SalesListOut>("/api/v1/sales/lead-finder/lists", {
        method: "POST",
        body: { name, list_type: listType },
      }),
    onSuccess: () => {
      setName("");
      queryClient.invalidateQueries({ queryKey: ["sales", "lead-finder", "lists"] });
    },
  });

  const columns: DataTableColumn<SalesListOut>[] = [
    {
      key: "name",
      header: "List",
      render: (list) => <span className="font-medium">{list.name}</span>,
      sortValue: (list) => list.name.toLowerCase(),
    },
    {
      key: "type",
      header: "Type",
      render: (list) => <Badge variant="outline">{list.list_type}</Badge>,
    },
    {
      key: "shared",
      header: "Shared",
      render: (list) => (list.is_shared ? <Badge variant="secondary">Shared</Badge> : "—"),
    },
    {
      key: "tags",
      header: "Tags",
      render: (list) => (
        <div className="flex flex-wrap gap-1">
          {list.tags.map((tag) => (
            <Badge key={tag} variant="outline">
              {tag}
            </Badge>
          ))}
        </div>
      ),
    },
    {
      key: "updated_at",
      header: "Updated",
      render: (list) => new Date(list.updated_at).toLocaleDateString(),
      sortValue: (list) => list.updated_at,
    },
  ];

  return (
    <div>
      <PageHeader title="Lists" description="Company and people lists built from the Lead Finder." />

      <div className="mb-4 flex flex-wrap gap-2">
        <Input
          placeholder="New list name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && name.trim()) createList.mutate();
          }}
          className="max-w-sm"
        />
        <Select value={listType} onChange={(e) => setListType(e.target.value as "company" | "person")} className="w-36">
          <option value="company">Companies</option>
          <option value="person">People</option>
        </Select>
        <Button disabled={!name.trim() || createList.isPending} onClick={() => createList.mutate()}>
          Create list
        </Button>
      </div>

      <DataTable
        columns={columns}
        data={lists}
        getRowId={(list) => list.id}
        onRowClick={(list) => router.push(`/sales/lists/${list.id}`)}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
        emptyTitle="No lists yet"
        emptyDescription="Create a list here, or add results to one from the Lead Finder."
      />
    </div>
  );
}
