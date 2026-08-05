"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api";
import type { SaveCompanyOut, SavePersonOut } from "@/lib/types";

/** Direct manual entry (spec: manual entry alongside CSV import) — always
 * source-classified as "manual" server-side (save_service maps
 * provider="manual" to verification_status="user_entered"), never
 * presented as provider-verified. */
export function ManualEntryDialog({
  open,
  onOpenChange,
  recordType,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  recordType: "company" | "person";
  onCreated: () => void;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [industry, setIndustry] = useState("");
  const [employeeCount, setEmployeeCount] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [title, setTitle] = useState("");
  const [companyDomain, setCompanyDomain] = useState("");
  const [phone, setPhone] = useState("");

  function reset() {
    setName("");
    setDomain("");
    setIndustry("");
    setEmployeeCount("");
    setFullName("");
    setEmail("");
    setTitle("");
    setCompanyDomain("");
    setPhone("");
  }

  const createCompany = useMutation({
    mutationFn: () =>
      apiFetch<SaveCompanyOut>("/api/v1/sales/lead-finder/manual/company", {
        method: "POST",
        body: {
          name,
          domain: domain || undefined,
          industry: industry || undefined,
          employee_count: employeeCount ? Number(employeeCount) : undefined,
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sales", "accounts"] });
      onCreated();
      reset();
      onOpenChange(false);
    },
  });

  const createPerson = useMutation({
    mutationFn: () =>
      apiFetch<SavePersonOut>("/api/v1/sales/lead-finder/manual/person", {
        method: "POST",
        body: {
          full_name: fullName,
          email: email || undefined,
          title: title || undefined,
          company_domain: companyDomain || undefined,
          phone: phone || undefined,
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sales", "contacts"] });
      onCreated();
      reset();
      onOpenChange(false);
    },
  });

  const canSubmit = recordType === "company" ? name.trim().length > 0 : fullName.trim().length > 0;
  const pending = recordType === "company" ? createCompany.isPending : createPerson.isPending;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add {recordType === "company" ? "a company" : "a person"} manually</DialogTitle>
          <DialogDescription>
            Manually-entered records are labeled &quot;user entered&quot;, never as provider-verified.
          </DialogDescription>
        </DialogHeader>
        {recordType === "company" ? (
          <div className="flex flex-col gap-3">
            <div>
              <Label htmlFor="manual-company-name" className="mb-1 block text-xs">
                Name *
              </Label>
              <Input id="manual-company-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="manual-company-domain" className="mb-1 block text-xs">
                Domain
              </Label>
              <Input
                id="manual-company-domain"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                placeholder="acme.com"
              />
            </div>
            <div>
              <Label htmlFor="manual-company-industry" className="mb-1 block text-xs">
                Industry
              </Label>
              <Input
                id="manual-company-industry"
                value={industry}
                onChange={(e) => setIndustry(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="manual-company-employee-count" className="mb-1 block text-xs">
                Employee count
              </Label>
              <Input
                id="manual-company-employee-count"
                type="number"
                min={0}
                value={employeeCount}
                onChange={(e) => setEmployeeCount(e.target.value)}
              />
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <div>
              <Label htmlFor="manual-person-full-name" className="mb-1 block text-xs">
                Full name *
              </Label>
              <Input
                id="manual-person-full-name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="manual-person-email" className="mb-1 block text-xs">
                Email
              </Label>
              <Input
                id="manual-person-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="manual-person-title" className="mb-1 block text-xs">
                Title
              </Label>
              <Input id="manual-person-title" value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="manual-person-company-domain" className="mb-1 block text-xs">
                Company domain
              </Label>
              <Input
                id="manual-person-company-domain"
                value={companyDomain}
                onChange={(e) => setCompanyDomain(e.target.value)}
                placeholder="acme.com"
              />
            </div>
            <div>
              <Label htmlFor="manual-person-phone" className="mb-1 block text-xs">
                Phone
              </Label>
              <Input id="manual-person-phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
            </div>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!canSubmit || pending}
            onClick={() => (recordType === "company" ? createCompany.mutate() : createPerson.mutate())}
          >
            {pending ? "Saving…" : "Add"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
