"use client";

import { useRef } from "react";

/** Which lifecycle state a list is showing: the work, or the archive.
 *
 * A filter, not an action. The previous control rendered the selected
 * side as a filled primary button, which is the same thing the page uses
 * for "Create questionnaire" — so it read as *the button you press*
 * rather than *the tab you are on*, and the arrangement was easy to read
 * backwards. A segmented control inside its own container says "these
 * two are the same kind of thing and one of them is current".
 *
 * Lifecycle is a separate dimension from workflow status. A draft can be
 * archived and a completed questionnaire can be active; this control
 * filters the first and never touches the second.
 *
 * Real tabs, so the keyboard works the way people expect: arrows move
 * between them, Home and End jump to the ends, and only the selected tab
 * is in the tab order.
 */
export function LifecycleTabs({
  value,
  onChange,
  activeCount,
  archivedCount,
  label,
  idPrefix,
}: {
  value: "active" | "archived";
  onChange: (next: "active" | "archived") => void;
  /** Counts of the whole lifecycle state, not of the visible page. */
  activeCount?: number;
  archivedCount?: number;
  /** Names what is being filtered, for anybody not looking at the screen. */
  label: string;
  idPrefix: string;
}) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const tabs = [
    { key: "active" as const, text: "Active", count: activeCount },
    { key: "archived" as const, text: "Archived", count: archivedCount },
  ];

  const move = (from: number, to: number) => {
    const index = (to + tabs.length) % tabs.length;
    onChange(tabs[index].key);
    refs.current[index]?.focus();
    return from;
  };

  return (
    <div
      role="tablist"
      aria-label={label}
      className="inline-flex items-center gap-1 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-subtle)] p-1"
    >
      {tabs.map((tab, index) => {
        const selected = value === tab.key;
        return (
          <button
            key={tab.key}
            ref={(node) => {
              refs.current[index] = node;
            }}
            type="button"
            role="tab"
            id={`${idPrefix}-tab-${tab.key}`}
            aria-selected={selected}
            aria-controls={`${idPrefix}-panel`}
            // Only the selected tab is tabbable; arrows move within.
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.key)}
            onKeyDown={(event) => {
              if (event.key === "ArrowRight" || event.key === "ArrowDown") {
                event.preventDefault();
                move(index, index + 1);
              } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
                event.preventDefault();
                move(index, index - 1);
              } else if (event.key === "Home") {
                event.preventDefault();
                move(index, 0);
              } else if (event.key === "End") {
                event.preventDefault();
                move(index, tabs.length - 1);
              }
            }}
            className={`inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-sm)] px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)] ${
              selected
                ? "bg-[var(--bg-surface)] font-medium text-[var(--fg-default)] shadow-[var(--shadow-token-sm)]"
                : "text-[var(--fg-muted)] hover:text-[var(--fg-default)]"
            }`}
          >
            {tab.text}
            {tab.count !== undefined && (
              // The count carries its own contrast, so the selected tab
              // is not distinguished by colour alone.
              <span
                className={`rounded-full px-1.5 text-xs tabular-nums ${
                  selected
                    ? "bg-[var(--bg-subtle)] text-[var(--fg-default)]"
                    : "text-[var(--fg-subtle)]"
                }`}
              >
                {tab.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
