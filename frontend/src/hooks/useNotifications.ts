import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Persistent notification record (backend/app/api/routes/notifications.py).
 * GET ingests the latest cron run outcomes from the live jobs.json stores
 * before listing, so polling this query is what keeps the record growing.
 * Read state lives server-side (read_at), unlike the old localStorage-only
 * "seen" tracking.
 */

export const notificationSchema = z.object({
  id: z.string(),
  source: z.string(),
  severity: z.enum(["info", "success", "warning", "error"]),
  title: z.string(),
  message: z.string().nullable(),
  summary: z.string().nullable(),
  job_id: z.string().nullable(),
  job_name: z.string().nullable(),
  profile: z.string().nullable(),
  script_name: z.string().nullable(),
  occurred_at: z.string(),
  read_at: z.string().nullable(),
  created_at: z.string(),
});

export type AppNotification = z.infer<typeof notificationSchema>;

const notificationListSchema = z.object({
  notifications: z.array(notificationSchema),
  total: z.number(),
  unread_count: z.number(),
});

export type NotificationList = z.infer<typeof notificationListSchema>;

export const notificationKeys = {
  all: ["notifications"] as const,
  list: (filter: { unreadOnly?: boolean; severity?: string } = {}) =>
    ["notifications", filter] as const,
};

export function useNotifications(
  filter: { unreadOnly?: boolean; severity?: string } = {},
  options: { refetchInterval?: number } = {}
) {
  return useQuery({
    queryKey: notificationKeys.list(filter),
    queryFn: async () => {
      const params = new URLSearchParams({ limit: "200" });
      if (filter.unreadOnly) params.set("unread_only", "true");
      if (filter.severity) params.set("severity", filter.severity);
      const data = await apiClient.get<unknown>(`/api/v1/notifications?${params}`);
      return notificationListSchema.parse(data);
    },
    refetchInterval: options.refetchInterval ?? 60_000,
  });
}

export function useMarkNotificationsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { ids?: string[]; all?: boolean }) =>
      apiClient.post<unknown>("/api/v1/notifications/mark-read", payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: notificationKeys.all }),
  });
}

export type CleanupMode = { mode: "all" } | { mode: "keep_days"; keep_days: 15 | 30 };

export function useCleanupNotifications() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CleanupMode) =>
      apiClient.post<unknown>("/api/v1/notifications/cleanup", payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: notificationKeys.all }),
  });
}
