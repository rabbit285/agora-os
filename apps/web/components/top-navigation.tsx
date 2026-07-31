"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { GlobalCreateButton } from "@/components/global-create-button";
import { ModuleSwitcher } from "@/components/module-switcher";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import { useCurrentOrganization, useCurrentUser } from "@/lib/session";

export function TopNavigation() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [searchValue, setSearchValue] = useState("");
  const { data: user } = useCurrentUser();
  const { data: organization } = useCurrentOrganization();

  async function handleLogout() {
    await apiFetch("/api/v1/auth/logout", { method: "POST" });
    queryClient.clear();
    router.push("/login");
  }

  function handleSearchKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && searchValue.trim()) {
      router.push(`/search?q=${encodeURIComponent(searchValue.trim())}`);
    }
  }

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-neutral-200 bg-white px-6">
      <ModuleSwitcher />
      <div className="flex items-center gap-4">
        <GlobalCreateButton />
        <Input
          placeholder="Search everything…"
          value={searchValue}
          onChange={(e) => setSearchValue(e.target.value)}
          onKeyDown={handleSearchKeyDown}
          className="w-64"
        />
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
