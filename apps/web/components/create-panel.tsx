"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import { Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

/** A creation form that stays closed until asked for.
 *
 * The compliance screens used to lead every section with a permanently
 * open form — nine of them on one page, most of which the customer will
 * never use, all competing with the content they came to read. The form
 * is the same; it just no longer shouts. */
export function CreatePanel({
  label,
  title,
  children,
  disabled = false,
}: {
  /** The button. Say what will be created: "Register AI system". */
  label: string;
  /** Heading shown once the panel is open. Defaults to the button label. */
  title?: string;
  children: ReactNode;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <Button size="sm" variant="outline" disabled={disabled} onClick={() => setOpen(true)}>
        <Plus className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
        {label}
      </Button>
    );
  }

  return (
    // `w-full` so the open form takes the whole row rather than whatever
    // space is left beside it. Everywhere this sits in a block container
    // that is already its width; where it shares a row with a filter, it
    // wraps onto its own line instead of being squeezed into half of one.
    <Card className="mb-4 w-full">
      <CardContent className="pt-6">
        <div className="mb-3 flex items-center justify-between gap-2">
          <p className="text-sm font-medium text-[var(--fg-default)]">{title ?? label}</p>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setOpen(false)}
            aria-label="Close form"
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </div>
        {children}
      </CardContent>
    </Card>
  );
}
