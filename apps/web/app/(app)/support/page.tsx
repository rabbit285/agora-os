"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { DataTable, type DataTableColumn } from "@/components/data-table";
import { MetricCard } from "@/components/metric-card";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import type {
  SupportAnalytics,
  SupportCustomer,
  SupportTicket,
  TicketCategory,
  TicketPriority,
} from "@/lib/types";

function AnalyticsSection() {
  const { data: analytics } = useQuery<SupportAnalytics>({
    queryKey: ["support", "analytics"],
    queryFn: () => apiFetch<SupportAnalytics>("/api/v1/support/analytics"),
  });

  if (!analytics) return null;

  return (
    <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
      <MetricCard label="Open Tickets" value={String(analytics.open_tickets)} />
      <MetricCard label="Avg Resolution Time" value={`${analytics.average_resolution_hours}h`} />
      <MetricCard
        label="Avg CSAT"
        value={String(analytics.average_csat)}
        description={`${analytics.csat_response_count} responses`}
      />
      <MetricCard
        label="Avg QA Score"
        value={String(analytics.average_qa_score)}
        description={`${analytics.qa_score_count} reviews`}
      />
    </div>
  );
}

function CustomersSection() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");

  const { data: customers, isLoading, error, refetch } = useQuery<SupportCustomer[]>({
    queryKey: ["support", "customers"],
    queryFn: () => apiFetch<SupportCustomer[]>("/api/v1/support/customers"),
  });

  const createCustomer = useMutation({
    mutationFn: () =>
      apiFetch<SupportCustomer>("/api/v1/support/customers", {
        method: "POST",
        body: { name, email },
      }),
    onSuccess: () => {
      setName("");
      setEmail("");
      queryClient.invalidateQueries({ queryKey: ["support", "customers"] });
    },
  });

  const columns: DataTableColumn<SupportCustomer>[] = [
    {
      key: "name",
      header: "Customer",
      render: (customer) => (
        <div className="flex flex-col">
          <span className="font-medium">{customer.name}</span>
          <span className="text-xs text-[var(--fg-subtle)]">{customer.email}</span>
        </div>
      ),
      sortValue: (customer) => customer.name.toLowerCase(),
    },
    {
      key: "plan",
      header: "Plan",
      render: (customer) => customer.plan ?? "—",
    },
    {
      key: "status",
      header: "Status",
      render: (customer) => <StatusBadge status={customer.status} />,
    },
  ];

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Customers
      </h2>
      <div className="mb-4 flex gap-2">
        <Input placeholder="Customer name" value={name} onChange={(e) => setName(e.target.value)} />
        <Input placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <Button
          disabled={!name.trim() || !email.trim() || createCustomer.isPending}
          onClick={() => createCustomer.mutate()}
        >
          Add customer
        </Button>
      </div>
      <DataTable
        columns={columns}
        data={customers}
        getRowId={(customer) => customer.id}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
        emptyTitle="No customers yet"
      />
    </div>
  );
}

function TicketsSection({ customers }: { customers: SupportCustomer[] | undefined }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [customerId, setCustomerId] = useState("");
  const [subject, setSubject] = useState("");
  const [category, setCategory] = useState<TicketCategory>("general");
  const [priority, setPriority] = useState<TicketPriority>("medium");

  const { data: tickets, isLoading, error, refetch } = useQuery<SupportTicket[]>({
    queryKey: ["support", "tickets"],
    queryFn: () => apiFetch<SupportTicket[]>("/api/v1/support/tickets"),
  });

  const createTicket = useMutation({
    mutationFn: () =>
      apiFetch<SupportTicket>("/api/v1/support/tickets", {
        method: "POST",
        body: { customer_id: customerId, subject, category, priority },
      }),
    onSuccess: () => {
      setSubject("");
      setCategory("general");
      setPriority("medium");
      queryClient.invalidateQueries({ queryKey: ["support", "tickets"] });
    },
  });

  const columns: DataTableColumn<SupportTicket>[] = [
    {
      key: "subject",
      header: "Ticket",
      render: (ticket) => (
        <div className="flex flex-col">
          <span className="font-medium">{ticket.subject}</span>
          {ticket.related_alert_id && (
            <span className="text-xs text-[var(--critical-600)]">Linked security alert created</span>
          )}
        </div>
      ),
      sortValue: (ticket) => ticket.subject.toLowerCase(),
    },
    {
      key: "category",
      header: "Category",
      render: (ticket) => <StatusBadge status={ticket.category} />,
    },
    {
      key: "priority",
      header: "Priority",
      render: (ticket) => <StatusBadge status={ticket.priority} />,
    },
    {
      key: "status",
      header: "Status",
      render: (ticket) => <StatusBadge status={ticket.status} />,
    },
  ];

  return (
    <div>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Tickets
      </h2>
      <Card className="mb-4">
        <CardContent className="flex flex-wrap gap-2 pt-5">
          <Select value={customerId} onChange={(e) => setCustomerId(e.target.value)} className="w-56">
            <option value="">Select customer…</option>
            {customers?.map((customer) => (
              <option key={customer.id} value={customer.id}>
                {customer.name}
              </option>
            ))}
          </Select>
          <Input
            placeholder="Subject"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            className="min-w-[240px] flex-1"
          />
          <Select
            value={category}
            onChange={(e) => setCategory(e.target.value as TicketCategory)}
            className="w-40"
          >
            <option value="general">General</option>
            <option value="billing">Billing</option>
            <option value="technical">Technical</option>
            <option value="account">Account</option>
            <option value="security">Security</option>
          </Select>
          <Select
            value={priority}
            onChange={(e) => setPriority(e.target.value as TicketPriority)}
            className="w-32"
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="urgent">Urgent</option>
          </Select>
          <Button
            disabled={!customerId || !subject.trim() || createTicket.isPending}
            onClick={() => createTicket.mutate()}
          >
            Create ticket
          </Button>
        </CardContent>
        <CardContent className="pt-0 pb-4">
          <p className="text-xs text-[var(--fg-subtle)]">
            Tickets categorized &ldquo;Security&rdquo; automatically notify Security and are
            escalated to urgent priority.
          </p>
        </CardContent>
      </Card>
      <DataTable
        columns={columns}
        data={tickets}
        getRowId={(ticket) => ticket.id}
        onRowClick={(ticket) => router.push(`/support/tickets/${ticket.id}`)}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
        emptyTitle="No tickets yet"
      />
    </div>
  );
}

const SUB_PAGES = [
  { href: "/support/conversations", label: "Conversations" },
  { href: "/support/knowledge", label: "Knowledge Base" },
  { href: "/support/ai-agent", label: "AI Agent" },
];

export default function SupportPage() {
  const { data: customers } = useQuery<SupportCustomer[]>({
    queryKey: ["support", "customers"],
    queryFn: () => apiFetch<SupportCustomer[]>("/api/v1/support/customers"),
  });

  return (
    <div>
      <PageHeader
        title="Customer Support"
        description="Customers, tickets, and the Support → Security escalation hook."
        actions={
          <div className="flex flex-wrap gap-2">
            {SUB_PAGES.map((page) => (
              <Link key={page.href} href={page.href}>
                <Button variant="outline" size="sm">
                  {page.label}
                </Button>
              </Link>
            ))}
          </div>
        }
      />
      <AnalyticsSection />
      <CustomersSection />
      <TicketsSection customers={customers} />
    </div>
  );
}
