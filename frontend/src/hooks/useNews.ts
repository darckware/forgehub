import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * News report archive (backend/app/api/routes/news.py). Pure filesystem
 * read/delete of each profile's `reports/*.md` -- no DB table backs this,
 * same pattern as the rest of the filesystem-only proxy routers
 * (foundation.py, system_control.py, hindsight.py).
 */

export const newsReportSchema = z.object({
  profile: z.string(),
  filename: z.string(),
  title: z.string(),
  date: z.string().nullable(),
  modified_at: z.string(),
  size_bytes: z.number(),
  article_count: z.number(),
  preview: z.string(),
});

export type NewsReport = z.infer<typeof newsReportSchema>;

const newsReportListSchema = z.object({
  reports: z.array(newsReportSchema),
});

const newsReportContentSchema = z.object({
  profile: z.string(),
  filename: z.string(),
  title: z.string(),
  content: z.string(),
  modified_at: z.string(),
});

export type NewsReportContent = z.infer<typeof newsReportContentSchema>;

export const newsKeys = {
  list: ["news-reports"] as const,
};

export function useNewsReports() {
  return useQuery({
    queryKey: newsKeys.list,
    queryFn: async () => {
      const data = await apiClient.get<unknown>("/api/v1/news");
      return newsReportListSchema.parse(data).reports;
    },
  });
}

export function useNewsReportContent(report: { profile: string; filename: string } | null) {
  return useQuery({
    queryKey: [...newsKeys.list, "content", report?.profile, report?.filename],
    queryFn: async () => {
      const data = await apiClient.get<unknown>(
        `/api/v1/news/${encodeURIComponent(report!.profile)}/${encodeURIComponent(report!.filename)}`
      );
      return newsReportContentSchema.parse(data);
    },
    enabled: report !== null,
  });
}

export function useDeleteNewsReport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (report: { profile: string; filename: string }) =>
      apiClient.delete(
        `/api/v1/news/${encodeURIComponent(report.profile)}/${encodeURIComponent(report.filename)}`
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: newsKeys.list });
    },
  });
}

export function useDeleteAllNewsReports() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.delete("/api/v1/news"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: newsKeys.list });
    },
  });
}
