"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type {
  SupportCustomer,
  SupportTicket,
  TicketCategory,
  TicketPriority,
} from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-neutral-300 bg-white px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-400";

function CustomersSection() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");

  const { data: customers } = useQuery<SupportCustomer[]>({
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

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        Customers
      </h2>
      <Card className="mb-4">
        <CardContent className="flex gap-2 pt-6">
          <Input placeholder="Customer name" value={name} onChange={(e) => setName(e.target.value)} />
          <Input placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <Button
            disabled={!name.trim() || !email.trim() || createCustomer.isPending}
            onClick={() => createCustomer.mutate()}
          >
            Add customer
          </Button>
        </CardContent>
      </Card>
      {customers?.length === 0 && <p className="text-sm text-neutral-500">No customers yet.</p>}
      <div className="flex flex-col gap-2">
        {customers?.map((customer) => (
          <Card key={customer.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div>
                <div className="font-medium text-neutral-900">{customer.name}</div>
                <div className="text-xs text-neutral-400">{customer.email}</div>
              </div>
              <div className="flex items-center gap-2">
                {customer.plan && <span className="text-xs text-neutral-400">{customer.plan}</span>}
                <StatusBadge status={customer.status} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function TicketsSection({ customers }: { customers: SupportCustomer[] | undefined }) {
  const queryClient = useQueryClient();
  const [customerId, setCustomerId] = useState("");
  const [subject, setSubject] = useState("");
  const [category, setCategory] = useState<TicketCategory>("general");
  const [priority, setPriority] = useState<TicketPriority>("medium");

  const { data: tickets } = useQuery<SupportTicket[]>({
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

  return (
    <div>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        Tickets
      </h2>
      <Card className="mb-4">
        <CardContent className="flex flex-wrap gap-2 pt-6">
          <select
            className={selectClassName}
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
          >
            <option value="">Select customer…</option>
            {customers?.map((customer) => (
              <option key={customer.id} value={customer.id}>
                {customer.name}
              </option>
            ))}
          </select>
          <Input
            placeholder="Subject"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            className="min-w-[240px] flex-1"
          />
          <select
            className={selectClassName}
            value={category}
            onChange={(e) => setCategory(e.target.value as TicketCategory)}
          >
            <option value="general">General</option>
            <option value="billing">Billing</option>
            <option value="technical">Technical</option>
            <option value="account">Account</option>
            <option value="security">Security</option>
          </select>
          <select
            className={selectClassName}
            value={priority}
            onChange={(e) => setPriority(e.target.value as TicketPriority)}
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="urgent">Urgent</option>
          </select>
          <Button
            disabled={!customerId || !subject.trim() || createTicket.isPending}
            onClick={() => createTicket.mutate()}
          >
            Create ticket
          </Button>
        </CardContent>
        <CardContent className="pt-0 pb-4">
          <p className="text-xs text-neutral-400">
            Tickets categorized &ldquo;Security&rdquo; automatically notify Security and are
            escalated to urgent priority (spec section 35).
          </p>
        </CardContent>
      </Card>
      {tickets?.length === 0 && <p className="text-sm text-neutral-500">No tickets yet.</p>}
      <div className="flex flex-col gap-2">
        {tickets?.map((ticket) => (
          <Link key={ticket.id} href={`/support/tickets/${ticket.id}`}>
            <Card className="transition-colors hover:border-neutral-400">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-neutral-900">{ticket.subject}</div>
                  {ticket.related_alert_id && (
                    <div className="text-xs text-red-600">Linked security alert created</div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={ticket.category} />
                  <StatusBadge status={ticket.priority} />
                  <StatusBadge status={ticket.status} />
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

export default function SupportPage() {
  const { data: customers } = useQuery<SupportCustomer[]>({
    queryKey: ["support", "customers"],
    queryFn: () => apiFetch<SupportCustomer[]>("/api/v1/support/customers"),
  });

  return (
    <div>
      <PageHeader
        title="Customer Support"
        description="Customers, tickets, and the Support → Security escalation hook — spec sections 30-35."
      />
      <CustomersSection />
      <TicketsSection customers={customers} />
    </div>
  );
}
