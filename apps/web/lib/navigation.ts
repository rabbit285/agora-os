// Application navigation tree (spec section 6). `implemented: false` items
// render in the sidebar (so the module switcher always shows the full
// product) but link to /coming-soon instead of a working page or a dead
// link — see docs/ROUTES_AND_SCREENS.md and spec section 82 (No Fake
// Features).

export type NavItem = {
  label: string;
  href: string;
  implemented: boolean;
};

export type NavGroup = {
  label: string;
  items: NavItem[];
};

export const NAVIGATION: NavGroup[] = [
  {
    label: "Overview",
    items: [
      { label: "Dashboard", href: "/", implemented: true },
      { label: "AI Copilot", href: "/copilot", implemented: true },
      { label: "Tasks", href: "/tasks", implemented: true },
      { label: "Approvals", href: "/approvals", implemented: true },
    ],
  },
  {
    label: "Compliance",
    items: [{ label: "Compliance", href: "/compliance", implemented: true }],
  },
  {
    label: "Security",
    items: [{ label: "Security", href: "/security", implemented: true }],
  },
  {
    label: "Sales",
    items: [{ label: "Sales", href: "/sales", implemented: false }],
  },
  {
    label: "Support",
    items: [{ label: "Customer Support", href: "/support", implemented: false }],
  },
  {
    label: "Automation",
    items: [{ label: "Workflows", href: "/automation", implemented: false }],
  },
  {
    label: "Knowledge",
    items: [{ label: "Documents", href: "/knowledge", implemented: true }],
  },
  {
    label: "Settings",
    items: [
      { label: "Organization", href: "/settings/organization", implemented: true },
      { label: "Users", href: "/settings/users", implemented: true },
    ],
  },
];

export const MODULES = [
  { key: "overview", label: "Business Overview", href: "/", implemented: true },
  { key: "compliance", label: "Compliance", href: "/compliance", implemented: true },
  { key: "security", label: "Security", href: "/security", implemented: true },
  { key: "sales", label: "Sales", href: "/sales", implemented: false },
  { key: "support", label: "Support", href: "/support", implemented: false },
  { key: "automation", label: "Automation", href: "/automation", implemented: false },
];
