import { useEffect, useState } from "react";
import { AlertCircle, Loader2, Save, Settings2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { type AppConfig, useAppConfig, useUpdateAppConfig } from "@/hooks/useAppConfig";
import { useForgeRouterVirtualModels } from "@/hooks/useOrchestration";

// A handful of common IANA zones as <datalist> suggestions -- the field
// still accepts any valid zone name, typed or picked, validated by the
// backend (zoneinfo) on save.
const COMMON_TIMEZONES = [
  "America/Sao_Paulo",
  "America/New_York",
  "America/Los_Angeles",
  "Europe/Lisbon",
  "Europe/London",
  "UTC",
];

function linesToList(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export default function SettingsPage() {
  const { data, isLoading, isError, error } = useAppConfig();
  const updateConfig = useUpdateAppConfig();
  const { data: forgeRouterModels = [], isLoading: modelsLoading } = useForgeRouterVirtualModels();
  const [form, setForm] = useState<AppConfig | null>(null);

  // Only seeds `form` once the real config has loaded, and again whenever
  // it's replaced wholesale (e.g. after a save elsewhere) -- never
  // clobbers in-progress edits on every background refetch.
  useEffect(() => {
    if (data && !form) setForm(data);
  }, [data, form]);

  if (isLoading || !form) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading settings...
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
        <AlertCircle className="h-5 w-5 shrink-0" />
        Failed to load settings: {(error as Error)?.message ?? "unknown error"}
      </div>
    );
  }

  const dirty = data ? JSON.stringify(data) !== JSON.stringify(form) : false;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-3xl font-bold tracking-tight">
          <Settings2 className="h-7 w-7" />
          Settings
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          System defaults from forgehub.config -- not credentials (those live in .env). Saving rewrites that
          file and applies immediately, no restart needed.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">ForgeRouter virtual models</CardTitle>
          <CardDescription>
            Model IDs available to agents. Auto is the recommended primary model; explicit classes are useful when planning already knows the workload.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {modelsLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading models...</div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {forgeRouterModels.map((model) => (
                <div key={model.id} className="rounded-md border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <code className="text-sm font-medium">{model.id}</code>
                    {model.is_recommended_default && <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">recommended</span>}
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{model.description}</p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Git Control</CardTitle>
          <CardDescription>Fixed system entry System Control's Git Control card always offers.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="hermes_source_path">Hermes checkout path</Label>
            <Input
              id="hermes_source_path"
              value={form.hermes_source_path}
              onChange={(e) => setForm({ ...form, hermes_source_path: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="git_control_default_repo">Default repo key</Label>
            <Input
              id="git_control_default_repo"
              value={form.git_control_default_repo}
              onChange={(e) => setForm({ ...form, git_control_default_repo: e.target.value })}
            />
            <p className="text-xs text-muted-foreground">
              What Git Control falls back to when no repo is selected -- must resolve to an entry it can find
              ("hermes" or a registered project key), or status requests will fail.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Backups</CardTitle>
          <CardDescription>
            Hermes backups land flat here; each backup-enabled project gets its own subdirectory unless it sets
            its own location.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="backup_root">Backup root</Label>
            <Input
              id="backup_root"
              value={form.backup_root}
              onChange={(e) => setForm({ ...form, backup_root: e.target.value })}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Cleanup &amp; Trash</CardTitle>
          <CardDescription>
            "Run Cleanup" moves eligible files into the trash folder below; "Empty trash" is a separate action
            that permanently deletes what's in it.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="trash_root">Trash folder</Label>
            <Input
              id="trash_root"
              value={form.trash_root}
              onChange={(e) => setForm({ ...form, trash_root: e.target.value })}
            />
            <p className="text-xs text-muted-foreground">
              Independent of the external Hermes "foundation-clear" cron, which always empties its own hardcoded
              /root/trash on its own weekly schedule regardless of this setting.
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="cleanup_scan_root">Scan root</Label>
            <Input
              id="cleanup_scan_root"
              value={form.cleanup_scan_root}
              onChange={(e) => setForm({ ...form, cleanup_scan_root: e.target.value })}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="cleanup_prune_paths">Pruned paths (one per line)</Label>
              <Textarea
                id="cleanup_prune_paths"
                rows={5}
                value={form.cleanup_prune_paths.join("\n")}
                onChange={(e) => setForm({ ...form, cleanup_prune_paths: linesToList(e.target.value) })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="cleanup_prune_names">Pruned directory names (one per line)</Label>
              <Textarea
                id="cleanup_prune_names"
                rows={5}
                value={form.cleanup_prune_names.join("\n")}
                onChange={(e) => setForm({ ...form, cleanup_prune_names: linesToList(e.target.value) })}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">General</CardTitle>
          <CardDescription>Timezone used for timestamps ForgeHub itself generates (e.g. backup filenames).</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="timezone">Timezone</Label>
            <Input
              id="timezone"
              list="timezone-suggestions"
              value={form.timezone}
              onChange={(e) => setForm({ ...form, timezone: e.target.value })}
              placeholder="America/Sao_Paulo"
            />
            <datalist id="timezone-suggestions">
              {COMMON_TIMEZONES.map((tz) => (
                <option key={tz} value={tz} />
              ))}
            </datalist>
            <p className="text-xs text-muted-foreground">
              IANA zone name (e.g. America/Sao_Paulo for UTC-3). Validated on save.
            </p>
          </div>
        </CardContent>
      </Card>

      {updateConfig.isError && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          {(updateConfig.error as Error)?.message ?? "Failed to save settings"}
        </div>
      )}
      {updateConfig.isSuccess && !dirty && (
        <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm">
          Settings saved -- applied immediately, no restart needed.
        </div>
      )}

      <div className="flex justify-end gap-2">
        <Button variant="outline" disabled={!dirty || updateConfig.isPending} onClick={() => data && setForm(data)}>
          Reset
        </Button>
        <Button
          className="gap-2"
          disabled={!dirty || updateConfig.isPending}
          onClick={() => form && updateConfig.mutate(form)}
        >
          {updateConfig.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Save
        </Button>
      </div>
    </div>
  );
}
