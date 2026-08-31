/** Where a document opens.
 *
 * There is one Document Detail route, and the library row, a Copilot
 * citation, an evidence item and a search hit all open it. The server
 * composes the href wherever it can (app/core/routes.py) — prefer that,
 * and use this helper only where a surface holds a document id and the
 * payload carries no href.
 *
 * It exists as one function rather than a template string inlined in six
 * components because that is exactly how citations went on pointing at
 * `/knowledge/<id>` for months after that module was withdrawn: the URL
 * was built in the component, and nothing checked it against the routes
 * the product still had.
 */

/** Must match DOCUMENT_ROUTE in apps/api/app/core/routes.py. Asserted by
 * `lib/documents.test.ts`, which also checks the route file exists and
 * that it is not one the middleware retires. */
export const DOCUMENT_ROUTE = "/documents";

export function documentDetailHref(
  documentId: string,
  options: { passage?: string | null; section?: string | null } = {}
): string {
  const params = new URLSearchParams();
  if (options.passage) params.set("passage", options.passage);
  if (options.section) params.set("section", options.section);
  const query = params.toString();
  return `${DOCUMENT_ROUTE}/${documentId}${query ? `?${query}` : ""}`;
}
