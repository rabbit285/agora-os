"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { ChevronDown, ChevronsLeft, ChevronsRight, X } from "lucide-react";

import { Logo } from "@/components/logo";
import { useSidebar } from "@/components/sidebar-context";
import { NAVIGATION, type NavItem } from "@/lib/navigation";
import { useCurrentPermissions } from "@/lib/session";
import { cn } from "@/lib/utils";

function isItemVisible(item: NavItem, permissionSet: Set<string> | null): boolean {
  if (!item.permission || item.permission.length === 0) return true;
  // Permissions not loaded yet: show everything rather than flash-hide,
  // matches AuthGuard's own "don't render broken UI" discipline.
  if (permissionSet === null) return true;
  return item.permission.some((p) => permissionSet.has(p));
}

export function AppSidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
  const { data: permissions } = useCurrentPermissions();
  const permissionSet = permissions ? new Set(permissions) : null;
  const { mobileOpen, setMobileOpen } = useSidebar();

  return (
    <>
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-[var(--gray-950)]/40 md:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}
      <nav
        aria-label="Primary"
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex shrink-0 flex-col border-r border-[var(--border-default)] bg-[var(--bg-surface)] transition-transform duration-[var(--transition-base)] md:static md:z-auto md:translate-x-0 md:transition-[width]",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          "w-[var(--sidebar-width)]",
          collapsed ? "md:w-[var(--sidebar-width-collapsed)]" : "md:w-[var(--sidebar-width)]",
        )}
      >
        <div className="flex h-[var(--header-height)] shrink-0 items-center justify-between border-b border-[var(--border-default)] px-3">
          <Logo size="sm" markOnly={collapsed} href="/" />
          <button
            type="button"
            onClick={() => setMobileOpen(false)}
            aria-label="Close menu"
            className="ml-auto flex h-7 w-7 items-center justify-center rounded-[var(--radius-sm)] text-[var(--fg-muted)] hover:bg-[var(--bg-surface-hover)] hover:text-[var(--fg-default)] md:hidden"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => setCollapsed((v) => !v)}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="ml-auto hidden h-7 w-7 items-center justify-center rounded-[var(--radius-sm)] text-[var(--fg-muted)] hover:bg-[var(--bg-surface-hover)] hover:text-[var(--fg-default)] md:flex"
          >
            {collapsed ? (
              <ChevronsRight className="h-4 w-4" aria-hidden="true" />
            ) : (
              <ChevronsLeft className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
        </div>

        <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-2 py-3">
        {NAVIGATION.map((group) => {
          const visibleItems = group.items.filter((item) => isItemVisible(item, permissionSet));
          if (visibleItems.length === 0) return null;
          return (
            <div key={group.label} className="flex flex-col gap-0.5">
              {!collapsed && (
                <div className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-[var(--fg-subtle)]">
                  {group.label}
                </div>
              )}
              {visibleItems.map((item) => {
                const href = item.implemented
                  ? item.href
                  : `/coming-soon?module=${encodeURIComponent(item.label.toLowerCase())}`;
                const active =
                  item.implemented &&
                  (pathname === item.href || pathname.startsWith(`${item.href}/`));
                const hasChildren = item.children && item.children.length > 0;
                const groupOpen = openGroups[item.href] ?? active;
                const Icon = item.icon;

                return (
                  <div key={item.href}>
                    <div className="flex items-center">
                      <Link
                        href={href}
                        title={collapsed ? item.label : undefined}
                        onClick={() => setMobileOpen(false)}
                        className={cn(
                          "flex flex-1 items-center gap-2.5 rounded-[var(--radius-md)] px-2 py-1.5 text-sm transition-colors duration-[var(--transition-fast)]",
                          active
                            ? "bg-[var(--brand-primary-subtle)] font-medium text-[var(--brand-primary)]"
                            : "text-[var(--fg-muted)] hover:bg-[var(--bg-surface-hover)] hover:text-[var(--fg-default)]",
                          !item.implemented && "opacity-60",
                        )}
                      >
                        {Icon && <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />}
                        {!collapsed && (
                          <span className="truncate">
                            {item.label}
                            {!item.implemented && (
                              <span className="ml-2 text-[10px] uppercase text-[var(--fg-subtle)]">
                                soon
                              </span>
                            )}
                          </span>
                        )}
                      </Link>
                      {!collapsed && hasChildren && (
                        <button
                          type="button"
                          onClick={() =>
                            setOpenGroups((prev) => ({ ...prev, [item.href]: !groupOpen }))
                          }
                          aria-label={groupOpen ? `Collapse ${item.label}` : `Expand ${item.label}`}
                          aria-expanded={groupOpen}
                          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-[var(--radius-sm)] text-[var(--fg-subtle)] hover:bg-[var(--bg-surface-hover)]"
                        >
                          <ChevronDown
                            className={cn(
                              "h-3.5 w-3.5 transition-transform duration-[var(--transition-fast)]",
                              groupOpen && "rotate-180",
                            )}
                            aria-hidden="true"
                          />
                        </button>
                      )}
                    </div>
                    {!collapsed && hasChildren && groupOpen && (
                      <div className="ml-6 mt-0.5 flex flex-col gap-0.5 border-l border-[var(--border-default)] pl-2.5">
                        {item.children!.map((child) => {
                          const childActive = pathname === child.href;
                          return (
                            <Link
                              key={child.href}
                              href={child.implemented ? child.href : "/coming-soon"}
                              onClick={() => setMobileOpen(false)}
                              className={cn(
                                "truncate rounded-[var(--radius-sm)] px-2 py-1 text-[13px] transition-colors duration-[var(--transition-fast)]",
                                childActive
                                  ? "font-medium text-[var(--brand-primary)]"
                                  : "text-[var(--fg-muted)] hover:text-[var(--fg-default)]",
                              )}
                            >
                              {child.label}
                            </Link>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          );
        })}
        </div>
      </nav>
    </>
  );
}
