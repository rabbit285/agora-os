import type { MetadataRoute } from "next";

const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";

// Exactly the real public marketing routes — nothing under (auth) or
// (app), both of which are noindex'd at their own layout level.
const PUBLIC_PATHS = [
  "",
  "/features",
  "/solutions",
  "/trust",
  "/pricing",
  "/about",
  "/contact",
  "/privacy",
  "/terms",
  "/cookies",
];

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return PUBLIC_PATHS.map((path) => ({
    url: `${APP_URL}${path}`,
    lastModified: now,
  }));
}
