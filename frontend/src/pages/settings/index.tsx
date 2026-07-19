import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, Loader2, Save, Settings2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
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

// Languages the AI chat (Workspace tabs + Assistant drawer) can answer in
// -- mirrors the keys of backend core/config.py's
// CHAT_RESPONSE_LANGUAGE_NOTES (the PUT validator rejects anything else).
// To add a language: add its hidden instruction there, then its label
// here. The backend appends that instruction to each outgoing agent call;
// nothing visible changes in the transcript.
const CHAT_RESPONSE_LANGUAGES = [
  { value: "pt-BR", label: "Português (Brasil)" },
  { value: "en", label: "English" },
  { value: "es", label: "Español" },
  { value: "fr", label: "Français" },
  { value: "de", label: "Deutsch" },
  { value: "it", label: "Italiano" },
];

function linesToList(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export default function SettingsPage() {
  const { t } = useTranslation("settings");
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
        {t("settings.messages.loading")}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
        <AlertCircle className="h-5 w-5 shrink-0" />
        {t("settings.messages.error", { message: (error as Error)?.message ?? t("settings.messages.unknownError") })}
      </div>
    );
  }

  const dirty = data ? JSON.stringify(data) !== JSON.stringify(form) : false;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-3xl font-bold tracking-tight">
          <Settings2 className="h-7 w-7" />
          {t("settings.title")}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("settings.description")}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">{t("settings.tabs.forgeRouterModels")}</CardTitle>
          <CardDescription>
            {t("settings.tabs.forgeRouterModelsDescription")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {modelsLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> {t("settings.messages.loadingModels")}</div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {forgeRouterModels.map((model) => (
                <div key={model.id} className="rounded-md border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <code className="text-sm font-medium">{model.id}</code>
                    {model.is_recommended_default && <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">{t("settings.messages.recommended")}</span>}
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
          <CardTitle className="text-xl">{t("settings.tabs.gitControl")}</CardTitle>
          <CardDescription>{t("settings.tabs.gitControlDescription")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="hermes_source_path">{t("settings.gitControl.hermesSourcePath.label")}</Label>
            <Input
              id="hermes_source_path"
              value={form.hermes_source_path}
              onChange={(e) => setForm({ ...form, hermes_source_path: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="git_control_default_repo">{t("settings.gitControl.gitControlDefaultRepo.label")}</Label>
            <Input
              id="git_control_default_repo"
              value={form.git_control_default_repo}
              onChange={(e) => setForm({ ...form, git_control_default_repo: e.target.value })}
            />
            <p className="text-xs text-muted-foreground">
              {t("settings.gitControl.gitControlDefaultRepo.help")}
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">{t("settings.tabs.backups")}</CardTitle>
          <CardDescription>
            {t("settings.tabs.backupsDescription")}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="backup_root">{t("settings.backups.backupRoot.label")}</Label>
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
          <CardTitle className="text-xl">{t("settings.tabs.cleanup")}</CardTitle>
          <CardDescription>
            {t("settings.tabs.cleanupDescription")}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="trash_root">{t("settings.cleanup.trashRoot.label")}</Label>
            <Input
              id="trash_root"
              value={form.trash_root}
              onChange={(e) => setForm({ ...form, trash_root: e.target.value })}
            />
            <p className="text-xs text-muted-foreground">
              {t("settings.cleanup.trashRoot.help")}
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="cleanup_scan_root">{t("settings.cleanup.cleanupScanRoot.label")}</Label>
            <Input
              id="cleanup_scan_root"
              value={form.cleanup_scan_root}
              onChange={(e) => setForm({ ...form, cleanup_scan_root: e.target.value })}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="cleanup_prune_paths">{t("settings.cleanup.prunedPaths.label")}</Label>
              <Textarea
                id="cleanup_prune_paths"
                rows={5}
                value={form.cleanup_prune_paths.join("\n")}
                onChange={(e) => setForm({ ...form, cleanup_prune_paths: linesToList(e.target.value) })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="cleanup_prune_names">{t("settings.cleanup.prunedNames.label")}</Label>
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
          <CardTitle className="text-xl">{t("settings.tabs.aiChat")}</CardTitle>
          <CardDescription>
            {t("settings.tabs.aiChatDescription")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="max-w-sm space-y-2">
            <Label htmlFor="chat_response_language">{t("settings.aiChat.chatResponseLanguage.label")}</Label>
            <Select
              id="chat_response_language"
              value={form.chat_response_language}
              onChange={(e) => setForm({ ...form, chat_response_language: e.target.value })}
            >
              {CHAT_RESPONSE_LANGUAGES.map((lang) => (
                <option key={lang.value} value={lang.value}>
                  {lang.label}
                </option>
              ))}
            </Select>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">{t("settings.tabs.general")}</CardTitle>
          <CardDescription>{t("settings.general.timezone.cardDescription")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="timezone">{t("settings.general.timezone.label")}</Label>
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
              {t("settings.general.timezone.help")}
            </p>
          </div>
        </CardContent>
      </Card>

      {updateConfig.isError && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          {(updateConfig.error as Error)?.message ?? t("settings.messages.saveError")}
        </div>
      )}
      {updateConfig.isSuccess && !dirty && (
        <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm">
          {t("settings.messages.saved")}
        </div>
      )}

      <div className="flex justify-end gap-2">
        <Button variant="outline" disabled={!dirty || updateConfig.isPending} onClick={() => data && setForm(data)}>
          {t("settings.messages.reset")}
        </Button>
        <Button
          className="gap-2"
          disabled={!dirty || updateConfig.isPending}
          onClick={() => form && updateConfig.mutate(form)}
        >
          {updateConfig.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          {t("settings.messages.save")}
        </Button>
      </div>
    </div>
  );
}
