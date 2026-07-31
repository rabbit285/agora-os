"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import { NOTIFICATION_CHANNELS, type Notification, type NotificationPreference } from "@/lib/types";

const CHANNEL_AVAILABILITY: Record<string, { deliverable: boolean; note: string }> = {
  email: { deliverable: true, note: "Logged, not really emailed — no SMTP provider configured yet" },
  webhook: { deliverable: true, note: "Real HTTP POST if a webhook URL is set on Settings > Organization" },
  slack: { deliverable: false, note: "Not deliverable — the Slack connector is read-only (channels:read only)" },
  teams: { deliverable: false, note: "Not deliverable — no Microsoft Teams connector exists yet" },
};

function PreferencesSection() {
  const queryClient = useQueryClient();

  const { data: preferences } = useQuery<NotificationPreference[]>({
    queryKey: ["notifications", "preferences"],
    queryFn: () => apiFetch<NotificationPreference[]>("/api/v1/notifications/preferences"),
  });

  const setPreference = useMutation({
    mutationFn: ({ channel, enabled }: { channel: string; enabled: boolean }) =>
      apiFetch<NotificationPreference>("/api/v1/notifications/preferences", {
        method: "PUT",
        body: { channel, enabled },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications", "preferences"] }),
  });

  const enabledFor = (channel: string) =>
    preferences?.find((p) => p.channel === channel)?.enabled ?? false;

  return (
    <Card className="mb-6 max-w-2xl">
      <CardContent className="flex flex-col gap-3 pt-6">
        <div>
          <h2 className="text-sm font-semibold text-neutral-900">Channel preferences</h2>
          <p className="text-xs text-neutral-500">
            In-app notifications always appear here regardless of these settings (spec §66).
          </p>
        </div>
        {NOTIFICATION_CHANNELS.map((channel) => {
          const availability = CHANNEL_AVAILABILITY[channel];
          const enabled = enabledFor(channel);
          return (
            <div key={channel} className="flex items-center justify-between text-sm">
              <div>
                <span className="font-medium capitalize text-neutral-900">{channel}</span>
                {!availability.deliverable && (
                  <Badge variant="outline" className="ml-2">
                    Not deliverable
                  </Badge>
                )}
                <p className="text-xs text-neutral-400">{availability.note}</p>
              </div>
              <Button
                size="sm"
                variant={enabled ? "default" : "outline"}
                disabled={setPreference.isPending}
                onClick={() => setPreference.mutate({ channel, enabled: !enabled })}
              >
                {enabled ? "Enabled" : "Disabled"}
              </Button>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

export default function NotificationsPage() {
  const queryClient = useQueryClient();

  const { data: notifications, isLoading } = useQuery<Notification[]>({
    queryKey: ["notifications"],
    queryFn: () => apiFetch<Notification[]>("/api/v1/notifications"),
  });

  const markRead = useMutation({
    mutationFn: (id: string) =>
      apiFetch<Notification>(`/api/v1/notifications/${id}/read`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const unread = notifications?.filter((n) => n.read_at === null) ?? [];

  return (
    <div>
      <PageHeader
        title="Notifications"
        description={`${unread.length} unread. Spec §66 — in-app is always delivered; other channels are opt-in below.`}
      />

      <PreferencesSection />

      {isLoading && <p className="text-sm text-neutral-500">Loading…</p>}
      {notifications && notifications.length === 0 && (
        <p className="text-sm text-neutral-500">No notifications yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {notifications?.map((notification) => (
          <Card key={notification.id} className={notification.read_at === null ? "border-neutral-400" : undefined}>
            <CardContent className="flex items-center justify-between pt-6">
              <div>
                <div className="font-medium text-neutral-900">
                  {notification.link ? (
                    <Link href={notification.link} className="hover:underline">
                      {notification.title}
                    </Link>
                  ) : (
                    notification.title
                  )}
                </div>
                {notification.body && (
                  <p className="mt-1 text-sm text-neutral-600">{notification.body}</p>
                )}
                <div className="mt-1 flex items-center gap-2 text-xs text-neutral-400">
                  <span>{new Date(notification.created_at).toLocaleString()}</span>
                  {notification.channels_delivered.length > 1 && (
                    <span>
                      also delivered via {notification.channels_delivered.filter((c) => c !== "in_app").join(", ")}
                    </span>
                  )}
                </div>
              </div>
              {notification.read_at === null && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={markRead.isPending}
                  onClick={() => markRead.mutate(notification.id)}
                >
                  Mark read
                </Button>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
