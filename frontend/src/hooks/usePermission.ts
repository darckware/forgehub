import { useAuthStore, type ModulePermission } from "@/store/authStore";

const FULL_ACCESS: ModulePermission = {
  can_view: true,
  can_query: true,
  can_write: true,
  can_delete: true,
};

const NO_ACCESS: ModulePermission = {
  can_view: false,
  can_query: false,
  can_write: false,
  can_delete: false,
};

/**
 * Returns the permission flags for the given module.
 * Admin users always receive FULL_ACCESS regardless of their profile.
 */
export function usePermission(module: string): ModulePermission {
  const user = useAuthStore((s) => s.user);
  const permissions = useAuthStore((s) => s.permissions);

  if (!user) return NO_ACCESS;
  if (user.is_admin) return FULL_ACCESS;
  return permissions[module] ?? NO_ACCESS;
}
