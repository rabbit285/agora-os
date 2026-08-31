/** Focus styling for a link that wraps a whole card.
 *
 * These rows were keyboard-reachable already — they are anchors — but
 * showed only a hover border change, so a keyboard user could tab through
 * a list of controls with no idea which one they were on. Hover is not a
 * focus state, and a row that is clickable has to be visibly focusable.
 *
 * Kept in one place because it applies to every clickable row in the
 * product, and nine copies of a ring utility is how they drift apart.
 */
export const CARD_LINK_FOCUS =
  "block rounded-[var(--radius-lg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-app)]";
