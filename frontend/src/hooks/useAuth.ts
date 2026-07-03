import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useAuthStore, type AuthUser, type PermissionMap } from "@/store/authStore";

interface TokenOut {
  access_token: string;
  token_type: string;
  user: AuthUser;
  permissions: PermissionMap;
}

interface LoginPayload {
  username: string;
  password: string;
}

export function useLogin() {
  const setAuth = useAuthStore((s) => s.setAuth);
  const qc = useQueryClient();

  return useMutation<TokenOut, Error, LoginPayload>({
    mutationFn: async ({ username, password }) => {
      const form = new URLSearchParams();
      form.append("username", username);
      form.append("password", password);
      const base = (import.meta.env.VITE_API_URL as string | undefined) || window.location.origin;
      const res = await fetch(`${base}/api/v1/auth/token`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: form.toString(),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as { detail?: string }).detail ?? "Login failed");
      }
      return res.json();
    },
    onSuccess: (data) => {
      setAuth(data.access_token, data.user, data.permissions ?? {});
      qc.clear();
    },
  });
}

// ---- Users ----------------------------------------------------------------

export function useUsers() {
  return useQuery<AuthUser[]>({
    queryKey: ["users"],
    queryFn: () => apiClient.get("/api/v1/users"),
  });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation<AuthUser, Error, { username: string; password: string; email?: string; full_name?: string; is_admin?: boolean; profile_id?: string }>({
    mutationFn: (body) => apiClient.post("/api/v1/users", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation<AuthUser, Error, { id: string; body: Partial<{ email: string; full_name: string; is_active: boolean; is_admin: boolean; password: string; profile_id: string | null }> }>({
    mutationFn: ({ id, body }) => apiClient.patch(`/api/v1/users/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useDeleteUser() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => apiClient.delete(`/api/v1/users/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}

// ---- Self-service (current user) ------------------------------------------

/** Profile edit for the logged-in user (name/email/avatar) -- unlike
 * useUpdateUser, this doesn't require admin rights, and can't touch
 * password/is_admin/is_active/profile_id (see backend's SelfUserUpdate). */
export function useUpdateMe() {
  const updateUser = useAuthStore((s) => s.updateUser);
  return useMutation<AuthUser, Error, Partial<{ email: string; full_name: string; avatar_data_url: string | null }>>({
    mutationFn: (body) => apiClient.patch("/api/v1/users/me", body),
    onSuccess: (user) => updateUser(user),
  });
}

export function useChangeMyPassword() {
  return useMutation<void, Error, { current_password: string; new_password: string }>({
    mutationFn: (body) => apiClient.post("/api/v1/users/me/change-password", body),
  });
}

// ---- Profiles -------------------------------------------------------------

export interface ProfilePermission {
  module: string;
  can_view: boolean;
  can_query: boolean;
  can_write: boolean;
  can_delete: boolean;
}

export interface Profile {
  id: string;
  name: string;
  description: string | null;
  permissions: ProfilePermission[];
  created_at: string;
  updated_at: string;
}

export function useProfiles() {
  return useQuery<Profile[]>({
    queryKey: ["profiles"],
    queryFn: () => apiClient.get("/api/v1/profiles"),
  });
}

export function useCreateProfile() {
  const qc = useQueryClient();
  return useMutation<Profile, Error, { name: string; description?: string; permissions: ProfilePermission[] }>({
    mutationFn: (body) => apiClient.post("/api/v1/profiles", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });
}

export function useUpdateProfile() {
  const qc = useQueryClient();
  return useMutation<Profile, Error, { id: string; body: { name?: string; description?: string; permissions?: ProfilePermission[] } }>({
    mutationFn: ({ id, body }) => apiClient.patch(`/api/v1/profiles/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });
}

export function useDeleteProfile() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => apiClient.delete(`/api/v1/profiles/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });
}
