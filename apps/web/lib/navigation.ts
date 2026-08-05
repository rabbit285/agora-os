// Application navigation tree (spec section 6). `implemented: false` items
// render in the sidebar (so the module switcher always shows the full
// product) but link to /coming-soon instead of a working page or a dead
// link — see docs/ROUTES_AND_SCREENS.md and spec section 82 (No Fake
// Features). `permission` is an optional gate: the item is hidden entirely
// unless the current user holds at least one of the listed permission
// keys — omit it for anything readable by every org member.

import type { LucideIcon } from "lucide-react";
import {
  Bell,
  BookOpen,
  Boxes,
  Brain,
  Briefcase,
  Building2,
  Cpu,
  ClipboardCheck,
  CreditCard,
  Database,
  FileBarChart2,
  FileClock,
  Gauge,
  GitBranch,
  Headset,
  KeyRound,
  Lightbulb,
  Lock,
  Newspaper,
  Plug,
  ScrollText,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Users,
  Workflow,
} from "lucide-react";

export type NavItem = {
  label: string;
  href: string;
  implemented: boolean;
  icon?: LucideIcon;
  /** Any one of these permissions makes the item visible; omit for
   * everyone-can-read items. */
  permission?: string[];
  children?: NavItem[];
};

export type NavGroup = {
  label: string;
  items: NavItem[];
};

export const NAVIGATION: NavGroup[] = [
  {
    label: "Command Center",
    items: [
      { label: "Overview", href: "/", implemented: true, icon: Gauge },
      { label: "AI Copilot", href: "/copilot", implemented: true, icon: Sparkles },
      { label: "Tasks", href: "/tasks", implemented: true, icon: ClipboardCheck },
      { label: "Approvals", href: "/approvals", implemented: true, icon: ShieldCheck },
      { label: "Recommendations", href: "/recommendations", implemented: true, icon: Lightbulb },
      { label: "Daily Briefing", href: "/briefing", implemented: true, icon: Newspaper },
      { label: "Reports", href: "/reports", implemented: true, icon: FileBarChart2 },
      { label: "Notifications", href: "/notifications", implemented: true, icon: Bell },
    ],
  },
  {
    label: "Governance",
    items: [
      { label: "Compliance", href: "/compliance", implemented: true, icon: ScrollText },
      { label: "Security", href: "/security", implemented: true, icon: ShieldAlert },
    ],
  },
  {
    label: "Growth",
    items: [
      {
        label: "Sales",
        href: "/sales",
        implemented: true,
        icon: Briefcase,
        children: [
          {
            label: "Lead Finder",
            href: "/sales/lead-finder",
            implemented: true,
            permission: ["sales.lead_finder.view"],
          },
          { label: "ICP Builder", href: "/sales/icp", implemented: true },
          { label: "Sales Inbox", href: "/sales/inbox", implemented: true },
          { label: "Meetings", href: "/sales/meetings", implemented: true },
          { label: "Campaigns", href: "/sales/campaigns", implemented: true },
        ],
      },
    ],
  },
  {
    label: "Customer Operations",
    items: [
      {
        label: "Support",
        href: "/support",
        implemented: true,
        icon: Headset,
        children: [
          { label: "Conversations", href: "/support/conversations", implemented: true },
          { label: "Knowledge Base", href: "/support/knowledge", implemented: true },
          { label: "AI Agent", href: "/support/ai-agent", implemented: true },
        ],
      },
    ],
  },
  {
    label: "Operations",
    items: [
      {
        label: "Automation",
        href: "/automation",
        implemented: true,
        icon: Workflow,
        children: [
          { label: "Connections", href: "/automation/connections", implemented: true },
          { label: "Templates", href: "/automation/templates", implemented: true },
        ],
      },
      {
        label: "Integrations",
        href: "/settings/integrations",
        implemented: true,
        icon: Plug,
        permission: ["integrations.connections.manage"],
      },
    ],
  },
  {
    label: "Knowledge",
    items: [
      { label: "Documents", href: "/knowledge", implemented: true, icon: BookOpen },
      { label: "Knowledge Graph", href: "/knowledge/graph", implemented: true, icon: Boxes },
    ],
  },
  {
    label: "Administration",
    items: [
      {
        label: "Organization",
        href: "/settings/organization",
        implemented: true,
        icon: Building2,
      },
      {
        label: "Users",
        href: "/settings/users",
        implemented: true,
        icon: Users,
        permission: ["org.users.manage"],
      },
      {
        label: "Roles",
        href: "/settings/roles",
        implemented: true,
        icon: KeyRound,
        permission: ["org.users.manage"],
      },
      { label: "Billing", href: "/settings/billing", implemented: true, icon: CreditCard },
      { label: "AI Providers", href: "/settings/ai-providers", implemented: true, icon: Cpu },
      { label: "Business Memory", href: "/settings/memory", implemented: true, icon: Brain },
      { label: "Business Rules", href: "/settings/business-rules", implemented: true, icon: GitBranch },
      { label: "Data Management", href: "/settings/data-management", implemented: true, icon: Database },
      { label: "Audit Logs", href: "/settings/audit-logs", implemented: false, icon: FileClock },
      { label: "Security", href: "/settings/security", implemented: true, icon: Lock },
    ],
  },
];

export const MODULES = [
  { key: "overview", label: "Business Overview", href: "/", implemented: true },
  { key: "compliance", label: "Compliance", href: "/compliance", implemented: true },
  { key: "security", label: "Security", href: "/security", implemented: true },
  { key: "sales", label: "Sales", href: "/sales", implemented: true },
  { key: "support", label: "Support", href: "/support", implemented: true },
  { key: "automation", label: "Automation", href: "/automation", implemented: true },
];
