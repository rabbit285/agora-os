"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, ClipboardCheck, LogOut, Search, Settings, User as UserIcon } from "lucide-react";

import { CommandPalette } from "@/components/command-palette";
import { GlobalCreateButton } from "@/components/global-create-button";
import { ModuleSwitcher } from "@/components/module-switcher";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import { useCurrentOrganization, useCurrentUser } from "@/lib/session";
import type { Approval, Notification } from "@/lib/types";

function NavIconLink({
  href,
  label,
  icon: Icon,
  count,
}: {
  href: string;
  label: string;
  icon: typeof Bell;
  count?: number;
}) {
  return (
    <Link
      href={href}
      aria-label={count ? `${label} (${count} unread)` : label}
      className="relative flex h-8 w-8 items-center justify-center rounded-[var(--radius-md)] text-[var(--fg-muted)] transition-colors duration-[var(--transition-fast)] hover:bg-[var(--bg-surface-hover)] hover:text-[var(--fg-default)]"
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      {count !== undefined && count > 0 && (
        <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-[var(--critical-600)] px-1 text-[10px] font-medium text-white">
          {count > 99 ? "99+" : count}
        </span>
      )}
    </Link>
  );
}

export function TopNavigation() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [searchValue, setSearchValue] = useState("");
  const { data: user } = useCurrentUser();
  const { data: organization } = useCurrentOrganization();

  const { data: notifications } = useQuery<Notification[]>({
    queryKey: ["notifications"],
    queryFn: () => apiFetch<Notification[]>("/api/v1/notifications"),
    staleTime: 30_000,
  });
  const { data: approvals } = useQuery<Approval[]>({
    queryKey: ["approvals"],
    queryFn: () => apiFetch<Approval[]>("/api/v1/approvals"),
    staleTime: 30_000,
  });

  const unreadCount = notifications?.filter((n) => !n.read_at).length ?? 0;
  const pendingApprovalsCount = approvals?.filter((a) => a.status === "pending").length ?? 0;

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

  const initials = (user?.full_name ?? user?.email ?? "?")
    .split(/\s+/)
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <header className="flex h-[var(--header-height)] shrink-0 items-center justify-between gap-4 border-b border-[var(--border-default)] bg-[var(--bg-surface)] px-4">
      <ModuleSwitcher />
      <div className="flex items-center gap-2">
        <GlobalCreateButton />
        <div className="relative w-56">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--fg-subtle)]"
            aria-hidden="true"
          />
          <Input
            placeholder="Search… (⌘K)"
            value={searchValue}
            onChange={(e) => setSearchValue(e.target.value)}
            onKeyDown={handleSearchKeyDown}
            className="pl-8"
          />
        </div>
        <NavIconLink href="/approvals" label="Approvals" icon={ClipboardCheck} count={pendingApprovalsCount} />
        <NavIconLink href="/notifications" label="Notifications" icon={Bell} count={unreadCount} />

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              aria-label="User menu"
              className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--brand-primary-subtle)] text-xs font-semibold text-[var(--brand-primary)] transition-opacity duration-[var(--transition-fast)] hover:opacity-80"
            >
              {initials}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>
              <div className="flex flex-col">
                <span className="text-[var(--fg-default)]">{user?.full_name ?? user?.email}</span>
                {organization && (
                  <span className="font-normal text-[var(--fg-subtle)]">{organization.name}</span>
                )}
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild>
              <Link href="/settings/organization" className="flex items-center gap-2">
                <UserIcon className="h-3.5 w-3.5" aria-hidden="true" />
                Account
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href="/settings/security" className="flex items-center gap-2">
                <Settings className="h-3.5 w-3.5" aria-hidden="true" />
                Settings
              </Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem destructive onClick={handleLogout} className="flex items-center gap-2">
              <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
              Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <CommandPalette />
    </header>
  );
}
