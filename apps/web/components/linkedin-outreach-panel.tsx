"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Link2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";

/** Manual-only LinkedIn outreach (spec: no scraping, no automated
 * login/connection-requests/messaging, no unofficial API). This panel
 * does exactly three things: stores a profile URL a human pasted in,
 * opens it in a new tab for the human to act on themselves, and turns a
 * human-drafted message into a real Task assigned to the current user —
 * nothing here ever touches LinkedIn programmatically. */
export function LinkedInOutreachPanel({
  contactId,
  initialUrl,
}: {
  contactId: string;
  initialUrl: string | null;
}) {
  const queryClient = useQueryClient();
  const [url, setUrl] = useState(initialUrl ?? "");
  const [message, setMessage] = useState("");
  const [createdTaskId, setCreatedTaskId] = useState<string | null>(null);

  const createTask = useMutation({
    mutationFn: () =>
      apiFetch<{ task_id: string; linkedin_url: string | null }>(
        `/api/v1/sales/lead-finder/contacts/${contactId}/linkedin-task`,
        { method: "POST", body: { linkedin_url: url || undefined, message } },
      ),
    onSuccess: (result) => {
      setCreatedTaskId(result.task_id);
      setMessage("");
      queryClient.invalidateQueries({ queryKey: ["sales", "contacts", contactId] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });

  return (
    <Card className="mb-6">
      <CardContent className="pt-6">
        <h2 className="mb-2 flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          <Link2 className="h-3.5 w-3.5" aria-hidden="true" />
          LinkedIn Outreach
        </h2>
        <p className="mb-3 text-[11px] text-[var(--fg-muted)]">
          Manual only — no automated login, connection requests, or messaging. Paste an approved
          profile URL, open it yourself, and create a task for the message you send by hand.
        </p>
        <div className="flex flex-col gap-3">
          <div>
            <Label htmlFor={`linkedin-url-${contactId}`} className="mb-1 block text-xs">
              Profile URL
            </Label>
            <div className="flex gap-2">
              <Input
                id={`linkedin-url-${contactId}`}
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.linkedin.com/in/..."
                className="flex-1"
              />
              {url ? (
                <Button variant="outline" size="icon" asChild>
                  <a href={url} target="_blank" rel="noreferrer" aria-label="Open LinkedIn profile">
                    <ExternalLink className="h-4 w-4" />
                  </a>
                </Button>
              ) : (
                <Button variant="outline" size="icon" disabled aria-label="Open LinkedIn profile">
                  <ExternalLink className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>
          <div>
            <Label htmlFor={`linkedin-message-${contactId}`} className="mb-1 block text-xs">
              Draft message
            </Label>
            <Textarea
              id={`linkedin-message-${contactId}`}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Write the message you'll send manually on LinkedIn…"
              rows={3}
            />
          </div>
          <Button
            className="self-start"
            disabled={!message.trim() || createTask.isPending}
            onClick={() => createTask.mutate()}
          >
            {createTask.isPending ? "Creating task…" : "Create outreach task"}
          </Button>
          {createdTaskId && (
            <p className="text-xs text-[var(--success-700)]">
              Task created — find it on your Tasks list to send the message yourself.
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
