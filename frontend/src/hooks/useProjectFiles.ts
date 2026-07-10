import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

/**
 * Project working-directory file browser/editor -- backs the Projects
 * detail page's file tree (Project Delivery > Projects > a project with a
 * working_directory_path set). See backend/app/api/routes/project.py's
 * "Project file browser" section and host-bridge/app.py's /v1/fs/* routes
 * for why every actual filesystem op happens on the host, not here.
 */

export interface ProjectFileEntry {
  name: string;
  path: string;
  type: "file" | "dir";
  size: number | null;
}

export interface ProjectFileListing {
  path: string;
  entries: ProjectFileEntry[];
}

export interface ProjectFileContent {
  path: string;
  content: string;
}

const RESOURCE = (projectId: string) => `/api/v1/projects/${projectId}/files`;

export const projectFileKeys = {
  list: (projectId: string, path: string) => ["projects", projectId, "files", "list", path] as const,
  content: (projectId: string, path: string) => ["projects", projectId, "files", "content", path] as const,
};

export function useProjectFileList(projectId: string | undefined, path: string) {
  return useQuery({
    queryKey: projectFileKeys.list(projectId ?? "", path),
    queryFn: () => apiClient.get<ProjectFileListing>(RESOURCE(projectId!), { params: { path } }),
    enabled: Boolean(projectId),
  });
}

export function useProjectFileContent(projectId: string | undefined, path: string | undefined) {
  return useQuery({
    queryKey: projectFileKeys.content(projectId ?? "", path ?? ""),
    queryFn: () => apiClient.get<ProjectFileContent>(`${RESOURCE(projectId!)}/content`, { params: { path } }),
    enabled: Boolean(projectId && path),
  });
}

function useInvalidateProjectFiles(projectId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ["projects", projectId, "files"] });
}

export function useWriteProjectFile(projectId: string) {
  const invalidate = useInvalidateProjectFiles(projectId);
  return useMutation({
    mutationFn: ({ path, content }: { path: string; content: string }) =>
      apiClient.put<ProjectFileContent>(`${RESOURCE(projectId)}/content`, { content }, { params: { path } }),
    onSuccess: invalidate,
  });
}

export function useCreateProjectDirectory(projectId: string) {
  const invalidate = useInvalidateProjectFiles(projectId);
  return useMutation({
    mutationFn: (path: string) => apiClient.post<ProjectFileEntry>(`${RESOURCE(projectId)}/directory`, { path }),
    onSuccess: invalidate,
  });
}

export function useCreateProjectFile(projectId: string) {
  const invalidate = useInvalidateProjectFiles(projectId);
  return useMutation({
    mutationFn: (path: string) => apiClient.post<ProjectFileEntry>(`${RESOURCE(projectId)}/new`, { path }),
    onSuccess: invalidate,
  });
}

export function useRenameProjectFile(projectId: string) {
  const invalidate = useInvalidateProjectFiles(projectId);
  return useMutation({
    mutationFn: ({ path, newPath }: { path: string; newPath: string }) =>
      apiClient.patch<ProjectFileEntry>(RESOURCE(projectId), { path, new_path: newPath }),
    onSuccess: invalidate,
  });
}

export function useDeleteProjectFile(projectId: string) {
  const invalidate = useInvalidateProjectFiles(projectId);
  return useMutation({
    mutationFn: ({ path, recursive }: { path: string; recursive?: boolean }) =>
      apiClient.delete<void>(RESOURCE(projectId), { params: { path, recursive: recursive ?? false } }),
    onSuccess: invalidate,
  });
}
