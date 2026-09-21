import { create } from "zustand";
import { createJSONStorage, persist, type StateStorage } from "zustand/middleware";

const REMEMBER_ME_KEY = "forgehub-remember-me";

/** Whether the last login opted into surviving a closed browser -- the
 * "Stay logged in" checkbox on LoginPage.tsx (2026-08-15). Stored
 * unconditionally in localStorage (it's a UI preference, not anything
 * sensitive) so the checkbox can default to the user's last choice next
 * time they land on the login page, independent of whether they're
 * currently authenticated.
 *
 * Unset (the key has never been written, e.g. a session that predates
 * this checkbox) defaults to `true` -- before this existed, zustand's
 * persist middleware always used localStorage unconditionally, so
 * defaulting the *unset* case to anything else would silently log out
 * every already-logged-in user the moment this change ships. */
export function getRememberMe(): boolean {
  const stored = localStorage.getItem(REMEMBER_ME_KEY);
  return stored === null ? true : stored === "true";
}

export function setRememberMe(value: boolean): void {
  localStorage.setItem(REMEMBER_ME_KEY, value ? "true" : "false");
}

/** Routes the persisted auth state to localStorage (survives closing the
 * browser) when "Stay logged in" was checked, sessionStorage (cleared the
 * moment the tab/browser closes) otherwise. Checked on every read/write
 * rather than once at store creation, so a login's choice takes effect
 * immediately without needing a fresh page load. removeItem always clears
 * both -- logout (clearAuth) must not leave a stale copy behind in
 * whichever storage a previous, differently-checked login used. */
const authStorage: StateStorage = {
  getItem: (name) => (getRememberMe() ? localStorage : sessionStorage).getItem(name),
  setItem: (name, value) => (getRememberMe() ? localStorage : sessionStorage).setItem(name, value),
  removeItem: (name) => {
    localStorage.removeItem(name);
    sessionStorage.removeItem(name);
  },
};

export interface AuthUser {
  id: string;
  username: string;
  email: string | null;
  full_name: string | null;
  avatar_data_url: string | null;
  totp_enabled: boolean;
  is_active: boolean;
  is_admin: boolean;
  profile_id: string | null;
  ui_language: string;
}

export interface ModulePermission {
  can_view: boolean;
  can_query: boolean;
  can_write: boolean;
  can_delete: boolean;
}

export type PermissionMap = Record<string, ModulePermission>;
export type ActionPermissionMap = Record<string, boolean>;

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  permissions: PermissionMap;
  actions: ActionPermissionMap;
  setAuth: (token: string, user: AuthUser, permissions: PermissionMap, actions?: ActionPermissionMap) => void;
  updateUser: (patch: Partial<AuthUser>) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      permissions: {},
      actions: {},
      setAuth: (token, user, permissions, actions = {}) => set({ token, user, permissions, actions }),
      updateUser: (patch) => set((s) => (s.user ? { user: { ...s.user, ...patch } } : s)),
      clearAuth: () => set({ token: null, user: null, permissions: {}, actions: {} }),
    }),
    { name: "forgehub-auth", storage: createJSONStorage(() => authStorage) }
  )
);
