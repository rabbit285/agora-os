"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { LoadingSkeleton } from "@/components/loading-skeleton";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
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
      <CardContent className="flex flex-col gap-3 pt-5">
        <div>
          <h2 className="text-sm font-semibold text-[var(--fg-default)]">Channel preferences</h2>
          <p className="text-xs text-[var(--fg-subtle)]">
            In-app notifications always appear here regardless of these settings.
          </p>
        </div>
        {NOTIFICATION_CHANNELS.map((channel) => {
          const availability = CHANNEL_AVAILABILITY[channel];
          const enabled = enabledFor(channel);
          return (
            <div key={channel} className="flex items-center justify-between text-sm">
              <div>
                <span className="font-medium capitalize text-[var(--fg-default)]">{channel}</span>
                {!availability.deliverable && (
                  <Badge variant="outline" className="ml-2">
                    Not deliverable
                  </Badge>
                )}
                <p className="text-xs text-[var(--fg-subtle)]">{availability.note}</p>
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

  const {
    data: notifications,
    isLoading,
    error,
    refetch,
  } = useQuery<Notification[]>({
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
        description={`${unread.length} unread. In-app is always delivered; other channels are opt-in below.`}
      />

      <PreferencesSection />

      {isLoading && <LoadingSkeleton rows={4} />}
      {error && <ErrorState onRetry={() => refetch()} />}
      {!isLoading && !error && notifications && notifications.length === 0 && (
        <EmptyState title="No notifications yet." />
      )}
      {!isLoading && !error && notifications && notifications.length > 0 && (
        <div className="flex flex-col gap-2">
          {notifications.map((notification) => (
            <Card
              key={notification.id}
              className={cn(notification.read_at === null && "border-[var(--brand-primary)]")}
            >
              <CardContent className="flex items-center justify-between pt-5">
                <div>
                  <div className="font-medium text-[var(--fg-default)]">
                    {notification.link ? (
                      <Link href={notification.link} className="hover:underline">
                        {notification.title}
                      </Link>
                    ) : (
                      notification.title
                    )}
                  </div>
                  {notification.body && (
                    <p className="mt-1 text-sm text-[var(--fg-muted)]">{notification.body}</p>
                  )}
                  <div className="mt-1 flex items-center gap-2 text-xs text-[var(--fg-subtle)]">
                    <span>{new Date(notification.created_at).toLocaleString()}</span>
                    {notification.channels_delivered.length > 1 && (
                      <span>
                        also delivered via{" "}
                        {notification.channels_delivered.filter((c) => c !== "in_app").join(", ")}
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
      )}
    </div>
  );
}
