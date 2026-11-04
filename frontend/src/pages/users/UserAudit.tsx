import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type Event = { id: string; event: string; actor: string; created_at: string; details: { ip_address?: string; user_agent?: string } };

export default function UserAudit() {
  const { t } = useTranslation("users");
  const [open, setOpen] = useState(false);
  const [actor, setActor] = useState("");
  const [event, setEvent] = useState("");
  const { data, isLoading, isError } = useQuery({
    queryKey: ["users", "audit", actor, event], enabled: open,
    queryFn: () => apiClient.get<Event[]>("/api/v1/users/audit/events", { params: { actor: actor || undefined, event: event || undefined } }),
  });
  const kinds = ["login_accepted", "login_refused", "logout", "session_revoked", "sessions_revoked", "profile_changed", "password_changed", "two_factor_enabled", "two_factor_disabled"];
  return <section className="rounded-md border p-4 space-y-3">
    <Button type="button" variant="outline" onClick={() => setOpen(!open)}>{t("users.audit.title")}</Button>
    {open && <>
      <div className="grid gap-2 md:grid-cols-2">
        <Input aria-label={t("users.audit.actor")} placeholder={t("users.audit.actor")} value={actor} onChange={e => setActor(e.target.value)} />
        <select className="rounded-md border bg-background px-3 py-2 text-sm" aria-label={t("users.audit.event")} value={event} onChange={e => setEvent(e.target.value)}>
          <option value="">{t("users.audit.all")}</option>
          {kinds.map(kind => <option key={kind} value={kind}>{t(`users.audit.events.${kind}`)}</option>)}
        </select>
      </div>
      {isLoading && <p>{t("users.audit.loading")}</p>}
      {isError && <p role="alert">{t("users.audit.error")}</p>}
      <div className="space-y-2">{data?.map(row => <div key={row.id} className="rounded border p-2 text-sm break-words">
        <div>{t(`users.audit.events.${row.event}`)} · {row.actor}</div>
        <div className="text-muted-foreground">{new Date(row.created_at).toLocaleString()} · {row.details?.ip_address || "—"} · {row.details?.user_agent || "—"}</div>
      </div>)}</div>
    </>}
  </section>;
}
