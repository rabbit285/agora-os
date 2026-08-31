/** Does this read like one of the questions rather than the document?
 *
 * A questionnaire is the thing a customer sends; a question is a line
 * inside it. Titling the document "Do you encrypt customer data at rest?"
 * makes the list read as though somebody imported a single question, and
 * leaves the customer's security review with nothing to be named after.
 *
 * This is a hint, not a rule. It runs as somebody types, says what it
 * noticed, and never blocks the button — a title is free text and the
 * person writing it may well have a reason.
 *
 * The server keeps the same list in `app/compliance/customer_identity.py`,
 * where it does the load-bearing job: refusing to read a customer's name
 * out of a title that is really a question. That copy is the one that
 * matters; this one only decides whether to show a sentence. They are
 * allowed to drift a little without anything breaking.
 */
const INTERROGATIVE = new Set([
  "do", "does", "did", "is", "are", "was", "were", "am",
  "can", "could", "will", "would", "shall", "should", "may", "might",
  "have", "has", "had",
  "how", "what", "which", "who", "whom", "whose",
  "where", "when", "why",
  "please", "describe", "explain", "list", "provide", "confirm",
  "detail", "outline", "state", "specify", "attach", "upload",
]);

export function looksLikeAQuestion(title: string): boolean {
  const trimmed = title.trim();
  if (!trimmed) return false;
  if (trimmed.endsWith("?")) return true;
  const first = trimmed.split(/[^\w'-]+/u)[0]?.toLowerCase() ?? "";
  return INTERROGATIVE.has(first);
}
