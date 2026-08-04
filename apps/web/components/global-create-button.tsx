"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { useCurrentPermissions } from "@/lib/session";

type CreateOption = {
  label: string;
  permission: string;
  href: string;
};

// spec §72 Global Create — one shortcut per named entity, filtered to what
// the current user's role can actually create (the same permission keys
// `require_permission()` enforces server-side, fetched via
// GET /organizations/current/my-permissions). Every option navigates to the
// module page that already owns that entity's real creation form, rather
// than duplicating 13 miniature forms here — several of these (Campaign,
// Support Ticket, DSAR) need reference pickers (a Sequence, a Customer)
// that only make sense in their module's own context anyway. "Document"
// goes to Knowledge's real upload flow rather than a bare file input here;
// "Report" goes to the Reporting module's own generate flow (spec §65,
// PLAT-20) for the same reason.
const CREATE_OPTIONS: CreateOption[] = [
  { label: "Task", permission: "core.tasks.manage", href: "/tasks" },
  { label: "Lead", permission: "sales.leads.manage", href: "/sales" },
  { label: "Account", permission: "sales.accounts.manage", href: "/sales" },
  { label: "Campaign", permission: "sales.sequences.manage", href: "/sales/campaigns" },
  { label: "Support Ticket", permission: "support.tickets.manage", href: "/support" },
  { label: "AI System", permission: "compliance.ai_systems.manage", href: "/compliance" },
  { label: "Risk", permission: "compliance.risks.manage", href: "/compliance" },
  { label: "Vendor", permission: "compliance.vendors.manage", href: "/compliance" },
  { label: "Policy", permission: "compliance.policies.manage", href: "/compliance" },
  { label: "DPIA", permission: "compliance.privacy.manage", href: "/compliance" },
  { label: "DSAR", permission: "compliance.privacy.manage", href: "/compliance" },
  { label: "Workflow", permission: "automation.workflows.manage", href: "/automation" },
  { label: "Document", permission: "knowledge.documents.manage", href: "/knowledge" },
  { label: "Report", permission: "reports.generate", href: "/reports" },
];

export function GlobalCreateButton() {
  const router = useRouter();
  const { data: permissions } = useCurrentPermissions();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const permissionSet = new Set(permissions ?? []);
  const availableOptions = CREATE_OPTIONS.filter((option) => permissionSet.has(option.permission));

  if (availableOptions.length === 0) {
    return null;
  }

  return (
    <div ref={containerRef} className="relative">
      <Button size="sm" onClick={() => setOpen((v) => !v)}>
        Create ▾
      </Button>
      {open && (
        <div className="absolute left-0 z-20 mt-1 w-48 rounded-md border border-neutral-200 bg-white py-1 shadow-lg">
          {availableOptions.map((option) => (
            <button
              key={option.label}
              className="block w-full px-3 py-1.5 text-left text-sm text-neutral-700 hover:bg-neutral-100"
              onClick={() => {
                setOpen(false);
                router.push(option.href);
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
