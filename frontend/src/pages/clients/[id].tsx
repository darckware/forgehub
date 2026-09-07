import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, CircleOff, Laptop, Loader2, Network, ShieldCheck } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useClient } from "@/hooks/useClients";
import { useCreatePeerGrant, usePeerGrants, useRevokePeerGrant, type PeerGrant } from "@/hooks/usePeerGrants";
import { useWorkstations, type Workstation } from "@/hooks/useWorkstations";
import { cn } from "@/lib/utils";

interface WorkstationPair {
  a: Workstation;
  b: Workstation;
  grant?: PeerGrant;
}

function displayName(workstation: Workstation, fallback: string) {
  return workstation.hostname?.trim() || `${fallback} ${workstation.id.slice(0, 8)}`;
}

function activeGrantFor(pair: Pick<WorkstationPair, "a" | "b">, grants: PeerGrant[]) {
  return grants.find((grant) => {
    if (grant.revoked_at) return false;
    return (
      (grant.workstation_a_id === pair.a.id && grant.workstation_b_id === pair.b.id) ||
      (grant.workstation_a_id === pair.b.id && grant.workstation_b_id === pair.a.id)
    );
  });
}

function pairsFor(workstations: Workstation[], grants: PeerGrant[]): WorkstationPair[] {
  const pairs: WorkstationPair[] = [];
  for (let first = 0; first < workstations.length; first += 1) {
    for (let second = first + 1; second < workstations.length; second += 1) {
      const pair = { a: workstations[first], b: workstations[second] };
      pairs.push({ ...pair, grant: activeGrantFor(pair, grants) });
    }
  }
  return pairs;
}

export default function ClientDetailPage() {
  const { id = "" } = useParams();
  const { t } = useTranslation("clients");
  const client = useClient(id);
  const workstations = useWorkstations(id);
  const grants = usePeerGrants(id);
  const createGrant = useCreatePeerGrant();
  const revokeGrant = useRevokePeerGrant();
  const [pendingPair, setPendingPair] = useState<string | null>(null);
  const [revokePair, setRevokePair] = useState<WorkstationPair | null>(null);

  const pairs = useMemo(
    () => pairsFor(workstations.data ?? [], grants.data ?? []),
    [workstations.data, grants.data],
  );

  useEffect(() => {
    document.title = `${client.data?.name ?? t("detail.title")} — ForgeHub`;
  }, [client.data?.name, t]);

  if (client.isLoading) {
    return <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status"><Loader2 className="h-4 w-4 motion-safe:animate-spin" />{t("states.loading")}</p>;
  }
  if (client.isError || !client.data) {
    return <div role="alert"><p className="font-medium text-destructive">{t("states.clientLoadError")}</p><Link to="/clients" className="mt-3 inline-flex items-center gap-1 text-sm underline"><ArrowLeft className="h-4 w-4" />{t("detail.back")}</Link></div>;
  }

  const workstationName = (item: Workstation) => displayName(item, t("detail.workstations.unnamed"));
  const mutationError = createGrant.error || revokeGrant.error;

  function grant(pair: WorkstationPair) {
    const key = `${pair.a.id}:${pair.b.id}`;
    setPendingPair(key);
    createGrant.mutate(
      { workstationAId: pair.a.id, workstationBId: pair.b.id },
      { onSettled: () => setPendingPair(null) },
    );
  }

  function confirmRevoke() {
    if (!revokePair?.grant) return;
    const key = `${revokePair.a.id}:${revokePair.b.id}`;
    setPendingPair(key);
    revokeGrant.mutate(revokePair.grant.id, {
      onSuccess: () => setRevokePair(null),
      onSettled: () => setPendingPair(null),
    });
  }

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6">
      <Breadcrumb items={[{ label: t("list.title"), href: "/clients" }, { label: client.data.name }]} />

      <header>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{client.data.name}</h1>
          <Badge variant="outline">{client.data.support_plan ? t(`supportPlans.${client.data.support_plan}`) : t("supportPlans.none")}</Badge>
        </div>
        <p className="mt-2 font-mono text-xs text-muted-foreground">{client.data.id}</p>
      </header>

      <section className="overflow-hidden rounded-lg border border-border bg-card" aria-labelledby="client-info-heading">
        <div className="border-b border-border px-5 py-4"><h2 id="client-info-heading" className="text-sm font-semibold">{t("detail.info.title")}</h2></div>
        <dl className="grid divide-y divide-border sm:grid-cols-2 sm:divide-x sm:divide-y-0 lg:grid-cols-4">
          {[
            [t("detail.info.contact"), client.data.contact_name],
            [t("detail.info.email"), client.data.contact_email],
            [t("detail.info.phone"), client.data.contact_phone],
            [t("detail.info.tag"), client.data.headscale_tag],
          ].map(([label, value]) => (
            <div key={label} className="min-w-0 px-4 py-3">
              <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
              <dd className={cn("mt-1 truncate text-sm", label === t("detail.info.tag") && "font-mono text-xs")} title={value ?? undefined}>{value || t("common.notProvided")}</dd>
            </div>
          ))}
        </dl>
        {client.data.notes && <p className="border-t border-border px-4 py-3 text-sm text-muted-foreground">{client.data.notes}</p>}
      </section>

      <section className="overflow-hidden rounded-lg border border-border bg-card" aria-labelledby="workstations-heading">
        <div className="flex items-center gap-2 border-b border-border px-5 py-4">
          <Laptop className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <h2 id="workstations-heading" className="text-sm font-semibold">{t("detail.workstations.title")}</h2>
          <Badge variant="secondary">{workstations.data?.length ?? 0}</Badge>
        </div>
        {workstations.isLoading ? (
          <p className="p-5 text-sm text-muted-foreground" role="status">{t("states.loading")}</p>
        ) : workstations.isError ? (
          <div className="p-5" role="alert"><p className="text-sm text-destructive">{t("states.workstationsLoadError")}</p><Button variant="outline" size="sm" className="mt-3" onClick={() => workstations.refetch()}>{t("common.retry")}</Button></div>
        ) : !workstations.data?.length ? (
          <p className="p-5 text-sm text-muted-foreground">{t("detail.workstations.empty")}</p>
        ) : (
          <ul className="divide-y divide-border">
            {workstations.data.map((item) => (
              <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
                <div><p className="text-sm font-medium">{workstationName(item)}</p><p className="font-mono text-xs text-muted-foreground">{item.id}</p></div>
                <Badge variant={item.device_token_active ? "success" : "outline"}>{item.device_token_active ? t("detail.workstations.active") : t("detail.workstations.revoked")}</Badge>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="overflow-hidden rounded-lg border border-border bg-card" aria-labelledby="communication-heading">
        <div className="border-b border-border px-5 py-4">
          <div className="flex items-center gap-2"><Network className="h-4 w-4 text-muted-foreground" aria-hidden="true" /><h2 id="communication-heading" className="text-sm font-semibold">{t("detail.communication.title")}</h2></div>
          <p className="mt-1 text-xs text-muted-foreground">{t("detail.communication.description")}</p>
        </div>

        {(grants.isLoading || workstations.isLoading) ? (
          <p className="p-5 text-sm text-muted-foreground" role="status">{t("states.loading")}</p>
        ) : grants.isError ? (
          <div className="p-5" role="alert"><p className="text-sm text-destructive">{t("states.grantsLoadError")}</p><Button variant="outline" size="sm" className="mt-3" onClick={() => grants.refetch()}>{t("common.retry")}</Button></div>
        ) : pairs.length === 0 ? (
          <div className="flex items-start gap-3 p-5 text-sm text-muted-foreground"><CircleOff className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" /><p>{t("detail.communication.empty")}</p></div>
        ) : (
          <ul className="divide-y divide-border">
            {pairs.map((pair) => {
              const pairKey = `${pair.a.id}:${pair.b.id}`;
              const connected = Boolean(pair.grant);
              const busy = pendingPair === pairKey;
              const aName = workstationName(pair.a);
              const bName = workstationName(pair.b);
              return (
                <li key={pairKey} className="grid gap-4 px-5 py-4 md:grid-cols-[minmax(0,1fr)_minmax(160px,.7fr)_minmax(0,1fr)_auto] md:items-center">
                  <div className="min-w-0"><p className="truncate text-sm font-medium">{aName}</p><p className="truncate font-mono text-xs text-muted-foreground">{pair.a.id}</p></div>
                  <div className="flex items-center gap-2" aria-hidden="true"><span className={cn("h-2 w-2 rounded-full", connected ? "bg-emerald-500" : "bg-muted-foreground/50")} /><span className={cn("h-px flex-1", connected ? "bg-emerald-500/60" : "bg-border")} /><span className="text-xs text-muted-foreground">{connected ? t("detail.communication.connected") : t("detail.communication.blocked")}</span><span className={cn("h-2 w-2 rounded-full", connected ? "bg-emerald-500" : "bg-muted-foreground/50")} /></div>
                  <div className="min-w-0"><p className="truncate text-sm font-medium">{bName}</p><p className="truncate font-mono text-xs text-muted-foreground">{pair.b.id}</p></div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={connected}
                    aria-label={t("detail.communication.toggleLabel", { a: aName, b: bName })}
                    aria-busy={busy}
                    disabled={busy || createGrant.isPending || revokeGrant.isPending}
                    onClick={() => connected ? setRevokePair(pair) : grant(pair)}
                    className={cn("relative h-7 w-12 cursor-pointer rounded-full border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50", connected ? "border-emerald-500/50 bg-emerald-500/25" : "border-border bg-muted")}
                  >
                    <span className={cn("absolute left-0 top-1 h-5 w-5 rounded-full bg-foreground transition-transform", connected ? "translate-x-5" : "translate-x-1")} />
                    {busy && <Loader2 className="absolute inset-0 m-auto h-3 w-3 motion-safe:animate-spin" aria-hidden="true" />}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {mutationError && <p className="border-t border-border px-5 py-3 text-sm text-destructive" role="alert">{t("detail.communication.changeError")}</p>}
      </section>

      <ConfirmDialog
        open={Boolean(revokePair)}
        title={t("detail.communication.revokeTitle")}
        description={revokePair ? t("detail.communication.revokeDescription", { a: workstationName(revokePair.a), b: workstationName(revokePair.b) }) : undefined}
        confirmLabel={t("detail.communication.revokeConfirm")}
        cancelLabel={t("common.cancel")}
        icon="warning"
        loading={revokeGrant.isPending}
        dismissDisabled={revokeGrant.isPending}
        error={revokeGrant.error ? t("detail.communication.changeError") : null}
        onConfirm={confirmRevoke}
        onCancel={() => setRevokePair(null)}
      >
        <p className="flex items-center gap-2 text-xs text-muted-foreground"><ShieldCheck className="h-4 w-4" aria-hidden="true" />{t("detail.communication.audited")}</p>
      </ConfirmDialog>
    </div>
  );
}
