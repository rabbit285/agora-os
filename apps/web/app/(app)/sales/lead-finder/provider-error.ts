import { ApiError } from "@/lib/api";

/**
 * Maps a Lead Finder search failure to an honest, actionable message keyed
 * off the real HTTP status the backend returned — never the raw provider
 * response or backend exception text (see
 * docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §3). Returns undefined for
 * anything not in this table so the caller falls back to the underlying
 * error's own message (still shown via the shared ErrorState component).
 */
export function describeProviderSearchError(
  error: unknown,
  searchLabel: "Company Search" | "People Search",
): Error | undefined {
  if (!(error instanceof ApiError)) return undefined;
  switch (error.status) {
    case 401:
      return new Error("Apollo authentication failed. Check the connected credential.");
    case 403:
      return new Error(`Your Apollo account or API key does not have access to ${searchLabel}.`);
    case 422:
      return new Error("One or more search filters are not supported by Apollo.");
    case 429:
      return new Error("Apollo rate limit reached. Please try again later.");
    default:
      return undefined;
  }
}
