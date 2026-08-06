import type { MetadataRoute } from "next";

const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";

// Belt-and-suspenders alongside each private route's own `robots: {index:
// false}` metadata (the mechanism search engines actually respect for a
// page they've already crawled) — this is the crawl-budget hint for
// pages they haven't reached yet.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: [
        "/login",
        "/signup",
        "/forgot-password",
        "/reset-password",
        "/verify-email",
        "/invite",
        "/mfa-challenge",
        "/onboarding",
        "/dashboard",
        "/tasks",
        "/approvals",
        "/compliance",
        "/security",
        "/sales",
        "/support",
        "/automation",
        "/knowledge",
        "/settings",
        "/copilot",
        "/search",
        "/notifications",
        "/reports",
        "/recommendations",
        "/briefing",
        "/coming-soon",
      ],
    },
    sitemap: `${APP_URL}/sitemap.xml`,
  };
}
