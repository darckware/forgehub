import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import i18n, { SUPPORTED_UI_LANGUAGES, type UiLanguage } from "@/i18n";
import { useAuthStore, type ActionPermissionMap, type AuthUser, type PermissionMap } from "@/store/authStore";

interface TokenOut {
  access_token: string;
  token_type: string;
  user: AuthUser;
  permissions: PermissionMap;
  actions: ActionPermissionMap;
}

interface LoginPayload {
  username: string;
  password: string;
}

export function useLogin() {
  const setAuth = useAuthStore((s) => s.setAuth);

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
      setAuth(data.access_token, data.user, data.permissions ?? {}, data.actions ?? {});
    },
  });
}

// Clears every cached query so a new login never shows the previous
// session's data. Called on logout (UserSettingsMenu's handleLogout), not
// on login success -- clearing there raced the fresh post-login navigation
// into AppLayout, which mounts several data-fetching widgets that expect a
// query cache to exist a moment before their first render, causing an
// intermittent blank screen recoverable only by a manual reload.
export function useClearQueryCacheOnLogout() {
  const qc = useQueryClient();
  return () => qc.clear();
}

// The JWT has a fixed 60-minute expiry (backend ACCESS_TOKEN_EXPIRE_MINUTES)
// with no server-side session state to extend -- left alone, an actively
// working user gets hard-redirected to /login the moment it lapses,
// regardless of how recently they moved the mouse (see lib/api.ts's 401
// handler). This makes the session "slide": any tracked activity event
// re-mints a fresh token via GET /auth/me (throttled so it isn't called on
// every mousemove), well inside the expiry window, for as long as the user
// keeps interacting. A truly idle tab still expires and gets logged out
// normally -- this only prevents the *false* logout of an active session.
const ACTIVITY_EVENTS = ["mousemove", "mousedown", "keydown", "wheel", "touchstart"] as const;
const REFRESH_MIN_INTERVAL_MS = 5 * 60 * 1000; // 12x margin inside the 60min token lifetime

export function useSessionKeepAlive() {
  const token = useAuthStore((s) => s.token);
  const setAuth = useAuthStore((s) => s.setAuth);
  const lastRefreshRef = useRef(0);

  useEffect(() => {
    if (!token) return;

    function onActivity() {
      const now = Date.now();
      if (now - lastRefreshRef.current < REFRESH_MIN_INTERVAL_MS) return;
      lastRefreshRef.current = now;
      apiClient
        .get<TokenOut>("/api/v1/auth/me")
        .then((data) => {
          if (data.access_token) setAuth(data.access_token, data.user, data.permissions ?? {}, data.actions ?? {});
        })
        .catch(() => {
          // Token already invalid -- lib/api.ts's 401 handler already
          // redirects to /login, nothing extra to do here.
        });
    }

    for (const evt of ACTIVITY_EVENTS) window.addEventListener(evt, onActivity, { passive: true });
    return () => {
      for (const evt of ACTIVITY_EVENTS) window.removeEventListener(evt, onActivity);
    };
  }, [token, setAuth]);
}

// Applies the logged-in user's saved ui_language to i18next -- covers
// initial load (zustand's persisted store rehydrates before this runs),
// login, and any change made elsewhere (e.g. UserSettingsMenu's language
// picker, which also calls i18n.changeLanguage directly for an instant
// switch; this hook is what makes that choice durable across reloads and
// other devices/browsers, where localStorage alone wouldn't carry it).
export function useSyncUiLanguage() {
  const uiLanguage = useAuthStore((s) => s.user?.ui_language);

  useEffect(() => {
    if (!uiLanguage) return;
    if (!(SUPPORTED_UI_LANGUAGES as readonly string[]).includes(uiLanguage)) return;
    if (i18n.language === uiLanguage) return;
    void i18n.changeLanguage(uiLanguage as UiLanguage);
  }, [uiLanguage]);
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
  return useMutation<AuthUser, Error, Partial<{ email: string; full_name: string; avatar_data_url: string | null; ui_language: UiLanguage }>>({
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
  action_permissions: { action_key: string; allowed: boolean }[];
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
  return useMutation<Profile, Error, { name: string; description?: string; permissions: ProfilePermission[]; action_permissions?: { action_key: string; allowed: boolean }[] }>({
    mutationFn: (body) => apiClient.post("/api/v1/profiles", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });
}

export function useUpdateProfile() {
  const qc = useQueryClient();
  return useMutation<Profile, Error, { id: string; body: { name?: string; description?: string; permissions?: ProfilePermission[]; action_permissions?: { action_key: string; allowed: boolean }[] } }>({
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
