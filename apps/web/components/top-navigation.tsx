"use client";

import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";

import { ModuleSwitcher } from "@/components/module-switcher";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import { useCurrentOrganization, useCurrentUser } from "@/lib/session";

export function TopNavigation() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: user } = useCurrentUser();
  const { data: organization } = useCurrentOrganization();

  async function handleLogout() {
    await apiFetch("/api/v1/auth/logout", { method: "POST" });
    queryClient.clear();
    router.push("/login");
  }

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-neutral-200 bg-white px-6">
      <ModuleSwitcher />
      <div className="flex items-center gap-4">
        {organization && (
          <span className="text-sm text-neutral-500">{organization.name}</span>
        )}
        {user && <span className="text-sm font-medium text-neutral-900">{user.full_name ?? user.email}</span>}
        <Button variant="outline" size="sm" onClick={handleLogout}>
          Log out
        </Button>
      </div>
    </header>
  );
}
