/**
 * The services a server publishes, expanded under its row in the inventory
 * (2026-08-14, Marcelo: "preciso ao clicar na linha abri o link dos serviços
 * de cada servidor, informando o Ip e porta de acesso... Exemplo:
 * 172.15.2.3:8000").
 *
 * Two ways in, as agreed: registering by hand is the record, and the scan icon
 * is the help — it reports which common ports answer, flags what is already
 * registered, and pre-fills the form for the rest. It never writes a row on
 * its own: an open port says something is listening, not what it is.
 *
 * Pure render of `useServerServicesViewModel`.
 */
import { ExternalLink, Loader2, Pencil, Plus, Radar, Trash2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useServerServicesViewModel } from "@/hooks/useServerServicesViewModel";
import type { Server } from "@/hooks/useServers";

export function ServerServicesPanel({ server }: { server: Server }) {
  const vm = useServerServicesViewModel(server.id);

  return (
    <div className="space-y-3 border-l-2 border-primary/40 bg-muted/20 px-6 py-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Services
          </h3>
          <span className="font-mono text-[11px] text-muted-foreground">{server.ip_address}</span>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            title={
              server.access_enabled
                ? "Scan common ports on this server"
                : "Access is turned off — turn it on to scan"
            }
            disabled={vm.status === "scanning" || !server.access_enabled}
            onClick={vm.scan}
          >
            {vm.status === "scanning" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Radar className="h-3.5 w-3.5" />
            )}
          </Button>
          <Button variant="outline" size="sm" className="h-7" onClick={vm.startCreate}>
            <Plus className="mr-1 h-3.5 w-3.5" />
            New service
          </Button>
        </div>
      </div>

      {vm.isLoading && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading services…
        </p>
      )}

      {!vm.isLoading && vm.services.length === 0 && vm.editing === null && (
        <p className="text-xs italic text-muted-foreground">
          No services registered. Add one, or scan for open ports.
        </p>
      )}

      {vm.services.length > 0 && (
        <ul className="space-y-1">
          {vm.services.map((service) => (
            <li
              key={service.id}
              className="flex items-center gap-2 rounded-md border border-border/60 bg-background/60 px-3 py-1.5"
            >
              <a
                href={service.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex min-w-0 flex-1 items-center gap-2 hover:underline"
                title={`Open ${service.url} in a new tab`}
              >
                <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <span className="truncate text-sm font-medium">{service.name}</span>
                <span className="truncate font-mono text-[11px] text-muted-foreground">
                  {service.url}
                </span>
              </a>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0"
                title="Edit service"
                onClick={() => vm.startEdit(service)}
              >
                <Pencil className="h-3 w-3" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0 text-destructive hover:text-destructive"
                title="Remove service"
                onClick={() => vm.requestDelete(service)}
              >
                <Trash2 className="h-3 w-3" />
              </Button>
            </li>
          ))}
        </ul>
      )}

      {vm.editing !== null && (
        <div className="space-y-2 rounded-md border border-border bg-background/60 p-3">
          <div className="flex items-center justify-between">
            <Label className="text-xs">{vm.editing === "new" ? "New service" : "Edit service"}</Label>
            <button
              type="button"
              onClick={vm.cancelEdit}
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="grid grid-cols-12 gap-2">
            <Input
              className="col-span-4 h-8"
              placeholder="Name (e.g. Moodle)"
              value={vm.draft.name}
              onChange={(e) => vm.setDraft({ name: e.target.value })}
            />
            <Select
              className="col-span-2 h-8"
              value={vm.draft.scheme}
              onChange={(e) => vm.setDraft({ scheme: e.target.value as "http" | "https" })}
            >
              <option value="http">http</option>
              <option value="https">https</option>
            </Select>
            <Input
              className="col-span-2 h-8 font-mono"
              type="number"
              placeholder="8000"
              value={vm.draft.port}
              onChange={(e) => vm.setDraft({ port: e.target.value })}
            />
            <Input
              className="col-span-4 h-8 font-mono"
              placeholder="/path (optional)"
              value={vm.draft.path}
              onChange={(e) => vm.setDraft({ path: e.target.value })}
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-[11px] text-muted-foreground">
              {vm.draft.scheme}://{server.ip_address}
              {vm.draft.port ? `:${vm.draft.port}` : ""}
              {vm.draft.path}
            </span>
            <Button
              size="sm"
              className="ml-auto h-7"
              disabled={!vm.canSave || vm.status === "saving"}
              onClick={vm.save}
            >
              {vm.status === "saving" && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
              Save
            </Button>
          </div>
        </div>
      )}

      {vm.scanResult && (
        <div className="space-y-1 rounded-md border border-dashed border-border p-3">
          <p className="text-[11px] text-muted-foreground">
            {vm.scanResult.length === 0
              ? `No open ports among the ${vm.scannedCount} checked.`
              : `${vm.scanResult.length} of ${vm.scannedCount} ports answered. Nothing was saved — pick one to register it.`}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {vm.scanResult.map((entry) => (
              <Badge
                key={entry.port}
                variant="outline"
                className={`gap-1 font-mono text-[10px] ${
                  entry.registered || !entry.likely_web ? "" : "cursor-pointer hover:bg-accent"
                }`}
                onClick={() => {
                  if (!entry.registered && entry.likely_web) vm.adoptFinding(entry);
                }}
                title={
                  entry.registered
                    ? "Already registered"
                    : entry.likely_web
                      ? "Register this port as a service"
                      : "Answers TCP but is not a web endpoint"
                }
              >
                :{entry.port}
                {entry.registered && <span className="text-emerald-500">✓</span>}
                {!entry.likely_web && <span className="text-muted-foreground">non-web</span>}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {vm.error && <p className="text-[11px] text-destructive">{vm.error}</p>}

      <ConfirmDialog
        open={vm.deleteTarget !== null}
        title="Remove service"
        description={
          vm.deleteTarget
            ? `Remove "${vm.deleteTarget.name}" (${vm.deleteTarget.url}) from ${server.name}? Only the ForgeHub entry is deleted — nothing on the server changes.`
            : ""
        }
        loading={vm.status === "deleting"}
        onConfirm={vm.confirmDelete}
        onCancel={vm.cancelDelete}
      />
    </div>
  );
}
