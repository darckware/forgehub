import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useUserConnections } from "./useUserConnections";

export default function UserConnections({ userId }: { userId: string }) {
  const { t } = useTranslation("users");
  const { query, revoke } = useUserConnections(userId);
  const [selected, setSelected] = useState<string | null | undefined>(undefined);
  const active = (query.data ?? []).filter(row => row.is_active && new Date(row.expires_at).getTime() > Date.now());
  return <section className="space-y-3 rounded-md border p-3">
    <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-medium">{t("users.connections.title")}</h2>
      {active.length > 0 && <Button size="sm" variant="outline" onClick={() => setSelected(null)}>{t("users.connections.endAll")}</Button>}</div>
    {query.isLoading && <p>{t("users.connections.loading")}</p>}
    {query.isError && <p role="alert">{t("users.connections.error")}</p>}
    {query.data && active.length === 0 && <p className="text-sm text-muted-foreground">{t("users.connections.empty")}</p>}
    {active.map(row => <div key={row.id} className="rounded border p-3 text-sm space-y-1 break-words">
      <div className="font-medium">{row.agent_name ? `svc-agente · ${row.agent_name}` : row.device_summary || t("users.connections.unknown")}{row.is_current && ` · ${t("users.connections.current")}`}</div>
      <div>{row.ip_address || "—"} · {row.user_agent || "—"}</div>
      <div>{t("users.connections.lastActivity")}: {new Date(row.last_activity_at).toLocaleString()}</div>
      <div>{t("users.connections.expires")}: {new Date(row.expires_at).toLocaleString()}</div>
      <Button variant="outline" size="sm" onClick={() => setSelected(row.id)}>{t("users.connections.end")}</Button>
    </div>)}
    <ConfirmDialog open={selected !== undefined} title={t(selected === null ? "users.connections.confirmAll" : "users.connections.confirmOne")}
      loading={revoke.isPending} error={revoke.error?.message} onCancel={() => setSelected(undefined)}
      onConfirm={() => { if (selected !== undefined) revoke.mutate(selected, { onSuccess: () => setSelected(undefined) }); }} />
  </section>;
}
