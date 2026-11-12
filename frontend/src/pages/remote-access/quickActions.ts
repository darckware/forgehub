/** Remote Access › Machines "Ações" (2026-11-11, plan
 * REMOTE_ACCESS_SUPPORT_ADJUSTMENTS_PLAN Fase 2 item 4): the quick actions
 * that used to be ten buttons above the list. The page owns what each one
 * opens (a panel, or the execution screen with a system script); the
 * machines card only lists them -- in the toolbar menu, and for one machine
 * in that machine's row menu, with the machine preselected. */
import type { Server } from "@/hooks/useServers";

/** System scripts the execution screen opens with (`?system=`). */
export const SYSTEM_ACTIONS = [
  "remote_access_install",
  "tailscale_install",
  "rustdesk_install",
  "rustdesk_get_id",
  "rustdesk_firewall",
  "rustdesk_password",
] as const;
export type SystemAction = (typeof SYSTEM_ACTIONS)[number];

export const ROTATIONS = ["rotate_login_password", "rotate_ssh_key"] as const;

export type QuickAction = "prepare" | (typeof ROTATIONS)[number] | "detect_os" | SystemAction;

export interface QuickActions {
  /** Runs an action; with a machine, that machine is preselected. */
  run: (action: QuickAction, machine?: Server) => void;
  detectOsPending: boolean;
}
