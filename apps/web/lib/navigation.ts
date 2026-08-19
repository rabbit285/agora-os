// Application navigation tree.
//
// Veyntra ships as a dedicated compliance platform. The sales, support,
// automation and knowledge-base modules are deliberately absent: their
// code remains in the repository and their tables still exist (DSAR data
// discovery reads them — personal data lives in those tables and a
// subject access request has to find it), but they are not part of the
// product a customer sees. `middleware.ts` rejects their routes so a
// stale bookmark cannot reach a screen the product no longer has.
//
// Every entry below resolves to a real page. Where a section of the
// stacked /compliance screen is the right destination, the link is an
// anchor into it rather than an invented route — only `[id]` detail
// routes exist beneath /compliance, so /compliance/frameworks would 404.
//
// `implemented: false` items render but link to /coming-soon rather than
// a dead link (spec section 82, No Fake Features). `permission` is an
// optional gate: the item is hidden entirely unless the current user
// holds at least one of the listed permission keys.

import type { LucideIcon } from "lucide-react";
import {
  Bell,
  BookOpen,
  Brain,
  Building2,
  ClipboardCheck,
  Cpu,
  CreditCard,
  Database,
  FileClock,
  Gauge,
  GitBranch,
  KeyRound,
  Plug,
  ScrollText,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Users,
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
    label: "Overview",
    items: [
      { label: "Dashboard", href: "/dashboard", implemented: true, icon: Gauge },
      { label: "Review Center", href: "/review", implemented: true, icon: ShieldCheck },
      { label: "Compliance Copilot", href: "/copilot", implemented: true, icon: Sparkles },
    ],
  },
  {
    label: "Compliance",
    items: [
      { label: "Documents", href: "/documents", implemented: true, icon: BookOpen },
      { label: "AI Systems", href: "/ai-systems", implemented: true, icon: Cpu },
      {
        label: "Frameworks",
        href: "/compliance#frameworks",
        implemented: true,
        icon: ScrollText,
      },
      {
        label: "Controls & Risk",
        href: "/compliance#controls",
        implemented: true,
        icon: ClipboardCheck,
      },
      {
        label: "Assessments",
        href: "/compliance#assessments",
        implemented: true,
        icon: FileClock,
      },
      { label: "Privacy", href: "/compliance#privacy", implemented: true, icon: Users },
      {
        label: "Vendors & Trust",
        href: "/compliance#vendors",
        implemented: true,
        icon: Building2,
      },
    ],
  },
  {
    label: "Act",
    items: [
      // Remediation *is* the shared task system — a compliance gap becomes
      // a Task with an owner and a due date. Labelled for what it does
      // here rather than for the table behind it.
      { label: "Remediation", href: "/tasks", implemented: true, icon: ClipboardCheck },
      { label: "Approvals", href: "/approvals", implemented: true, icon: ShieldCheck },
      { label: "Notifications", href: "/notifications", implemented: true, icon: Bell },
    ],
  },
  {
    label: "Assurance",
    items: [
      { label: "Security", href: "/security", implemented: true, icon: ShieldAlert },
      { label: "Integrations", href: "/integrations", implemented: true, icon: Plug },
      { label: "Audit Log", href: "/settings/audit-logs", implemented: true, icon: FileClock },
    ],
  },
  {
    label: "Settings",
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
      { label: "AI Providers", href: "/settings/ai-providers", implemented: true, icon: Brain },
      {
        label: "Business Rules",
        href: "/settings/business-rules",
        implemented: true,
        icon: GitBranch,
      },
      {
        label: "Data Management",
        href: "/settings/data-management",
        implemented: true,
        icon: Database,
      },
      {
        label: "Account Security",
        href: "/settings/security",
        implemented: true,
        icon: KeyRound,
      },
    ],
  },
];

export const MODULES = [
  { key: "overview", label: "Overview", href: "/dashboard", implemented: true },
  { key: "compliance", label: "Compliance", href: "/compliance", implemented: true },
  { key: "security", label: "Security", href: "/security", implemented: true },
];
