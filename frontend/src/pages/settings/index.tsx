import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, Check, Loader2, Save, Settings2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { TokenField } from "@/components/ui/token-field";
import { type AppConfig, useAppConfig, useUpdateAppConfig } from "@/hooks/useAppConfig";
import { useForgeRouterServices } from "@/hooks/useAgent";
import { useForgeRouterVirtualModels } from "@/hooks/useOrchestration";
import { useOpenclawGatewayToken, useUpdateOpenclawGatewayToken } from "@/hooks/useTerminalBrowse";

// Every IANA zone name as <datalist> suggestions (2026-07-29, Marcelo:
// "adicione o timezone para todos os países" -- the previous list only had
// 6 hand-picked entries). Intl.supportedValuesOf("timeZone") returns the
// full ~400-entry tz database the browser itself ships (all countries,
// every region), so there's no static list to maintain here. Falls back to
// a small hand-picked set for the rare pre-2022 browser that doesn't
// implement it -- the field still accepts any valid zone name typed by
// hand regardless, validated by the backend (zoneinfo) on save.
const FALLBACK_TIMEZONES = [
  "America/Sao_Paulo",
  "America/New_York",
  "America/Los_Angeles",
  "Europe/Lisbon",
  "Europe/London",
  "UTC",
];
// tsconfig's `lib` predates ES2022.Intl, so the ambient `Intl` type has no
// `supportedValuesOf` member yet even though every real target browser
// ships it -- narrow, local cast rather than bumping the project-wide lib
// target for one call site.
type IntlWithSupportedValuesOf = typeof Intl & { supportedValuesOf?: (key: "timeZone") => string[] };
const ALL_TIMEZONES: string[] =
  (Intl as IntlWithSupportedValuesOf).supportedValuesOf?.("timeZone") ?? FALLBACK_TIMEZONES;

// UTC offset per zone (e.g. "GMT-3") -- 2026-07-29, Marcelo: "adicione a
// diferença da hora: America/Sao_Paulo -3h". Computed once at module load,
// today's offset (DST-observing zones can differ by season, but this is a
// picker label, not a live clock). The <option>'s text content becomes the
// datalist suggestion's visible label in Chrome/Firefox while `value`
// (the bare zone name) stays what actually gets typed into the field.
function utcOffsetLabel(tz: string): string {
  try {
    const parts = new Intl.DateTimeFormat("en-US", { timeZone: tz, timeZoneName: "shortOffset" }).formatToParts(new Date());
    return parts.find((p) => p.type === "timeZoneName")?.value ?? "";
  } catch {
    return "";
  }
}
const TIMEZONE_OPTIONS: { tz: string; label: string }[] = ALL_TIMEZONES.map((tz) => ({
  tz,
  label: `${tz} (${utcOffsetLabel(tz)})`,
}));

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

// App shell language new users get on creation -- constrained by
// User.ui_language's own CheckConstraint (ck_users_ui_language, backend
// UI_LANGUAGES = ("en", "pt-BR", "es")); the PUT validator rejects
// anything outside that set. Not the full CHAT_RESPONSE_LANGUAGES list
// above -- the app shell itself (menus, screens, forms) only has en/pt-BR/
// es locale files (src/i18n/locales/), unlike the chat instruction, which
// just needs a language name in a hidden prompt note.
const DEFAULT_UI_LANGUAGES = [
  { value: "pt-BR", label: "Português (Brasil)" },
  { value: "en", label: "English" },
  { value: "es", label: "Español" },
];

function linesToList(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

/** Independent card, own load/save -- the OpenClaw gateway token isn't part
 * of AppConfig/forgehub.config (useAppConfig.ts: "not secrets -- those stay
 * in .env"). It lives in /root/.openclaw/.env on the host and is read/
 * written through its own host-bridge endpoint (2026-07-29), so it gets its
 * own query/mutation and Save button rather than joining the big form's
 * batched save below. */
function OpenclawTokenCard() {
  const { t } = useTranslation("settings");
  const { data, isLoading } = useOpenclawGatewayToken();
  const updateToken = useUpdateOpenclawGatewayToken();
  const [value, setValue] = useState("");
  const [seeded, setSeeded] = useState(false);

  useEffect(() => {
    if (data && !seeded) {
      setValue(data.token ?? "");
      setSeeded(true);
    }
  }, [data, seeded]);

  const dirty = seeded && value.trim() !== (data?.token ?? "");

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">{t("settings.tabs.openclaw")}</CardTitle>
        <CardDescription>{t("settings.tabs.openclawDescription")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="max-w-md space-y-2">
          <Label htmlFor="openclaw_gateway_token">{t("settings.openclaw.gatewayToken.label")}</Label>
          {isLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> {t("settings.messages.loading")}
            </div>
          ) : (
            <TokenField
              id="openclaw_gateway_token"
              value={value}
              onChange={setValue}
              placeholder={t("settings.openclaw.gatewayToken.placeholder")}
            />
          )}
          <p className="text-xs text-muted-foreground">{t("settings.openclaw.gatewayToken.help")}</p>
        </div>

        {updateToken.isError && (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            {(updateToken.error as Error)?.message ?? t("settings.messages.saveError")}
          </div>
        )}
        {updateToken.isSuccess && !dirty && (
          <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm">
            {t("settings.messages.saved")}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <Button
            variant="outline"
            disabled={!dirty || updateToken.isPending}
            onClick={() => setValue(data?.token ?? "")}
          >
            {t("settings.messages.reset")}
          </Button>
          <Button
            className="gap-2"
            disabled={!dirty || updateToken.isPending || !value.trim()}
            onClick={() => updateToken.mutate(value.trim())}
          >
            {updateToken.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            {t("settings.messages.save")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  const { t } = useTranslation("settings");
  const { data, isLoading, isError, error } = useAppConfig();
  const updateConfig = useUpdateAppConfig();
  const { data: forgeRouterModels = [], isLoading: modelsLoading } = useForgeRouterVirtualModels();
  const { data: forgeRouterServices = [] } = useForgeRouterServices();
  const [form, setForm] = useState<AppConfig | null>(null);
  const [languageSaveStatus, setLanguageSaveStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [languageSaveError, setLanguageSaveError] = useState<string | null>(null);

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

  // Language fields save immediately on change instead of waiting for the
  // page-level Save button (2026-07-29, Marcelo: "salva automático" --
  // after moving Save/Reset into this card wasn't enough, since the other
  // fields here already read as live). Still one full PUT under the hood
  // (this screen has no per-field endpoint), just fired eagerly with the
  // rest of the current form instead of batched behind a click.
  async function saveLanguageField(field: "default_ui_language" | "chat_response_language", value: string) {
    if (!form) return;
    const next = { ...form, [field]: value };
    setForm(next);
    setLanguageSaveError(null);
    setLanguageSaveStatus("saving");
    try {
      await updateConfig.mutateAsync(next);
      setLanguageSaveStatus("saved");
      setTimeout(() => setLanguageSaveStatus((s) => (s === "saved" ? "idle" : s)), 1500);
    } catch (err) {
      setLanguageSaveStatus("idle");
      setLanguageSaveError((err as Error)?.message ?? t("settings.messages.saveError"));
    }
  }

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
          <div className="mt-4 max-w-sm space-y-2 border-t pt-4">
            <Label htmlFor="default_forgerouter_service_name">{t("settings.forgeRouterModels.defaultAgent.label")}</Label>
            <Select
              id="default_forgerouter_service_name"
              value={form.default_forgerouter_service_name}
              onChange={(e) => setForm({ ...form, default_forgerouter_service_name: e.target.value })}
            >
              <option value="">{t("settings.forgeRouterModels.defaultAgent.none")}</option>
              {forgeRouterServices.map((service) => (
                <option key={service.name} value={service.name}>
                  {service.name}
                </option>
              ))}
            </Select>
            <p className="text-xs text-muted-foreground">{t("settings.forgeRouterModels.defaultAgent.help")}</p>
          </div>
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
          <CardTitle className="text-xl">{t("settings.tabs.agentRuntimePaths")}</CardTitle>
          <CardDescription>{t("settings.tabs.agentRuntimePathsDescription")}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          {Object.entries(form.agent_runtime_paths).map(([runtime, path]) => (
            <div className="space-y-2" key={runtime}>
              <Label htmlFor={`agent_runtime_path_${runtime}`}>{runtime}</Label>
              <Input
                id={`agent_runtime_path_${runtime}`}
                value={path}
                onChange={(e) =>
                  setForm({
                    ...form,
                    agent_runtime_paths: { ...form.agent_runtime_paths, [runtime]: e.target.value },
                  })
                }
              />
            </div>
          ))}
        </CardContent>
      </Card>

      <OpenclawTokenCard />

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
              <Textarea className="resize-none"
                id="cleanup_prune_paths"
                rows={5}
                value={form.cleanup_prune_paths.join("\n")}
                onChange={(e) => setForm({ ...form, cleanup_prune_paths: linesToList(e.target.value) })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="cleanup_prune_names">{t("settings.cleanup.prunedNames.label")}</Label>
              <Textarea className="resize-none"
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
        <CardContent className="space-y-6">
          <div className="max-w-sm space-y-2">
            <div className="flex items-center gap-2">
              <Label htmlFor="default_ui_language">{t("settings.aiChat.defaultUiLanguage.label")}</Label>
              {languageSaveStatus === "saving" && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
              {languageSaveStatus === "saved" && <Check className="h-3.5 w-3.5 text-emerald-500" />}
            </div>
            <Select
              id="default_ui_language"
              value={form.default_ui_language}
              onChange={(e) => saveLanguageField("default_ui_language", e.target.value)}
            >
              {DEFAULT_UI_LANGUAGES.map((lang) => (
                <option key={lang.value} value={lang.value}>
                  {lang.label}
                </option>
              ))}
            </Select>
            <p className="text-sm text-muted-foreground">{t("settings.aiChat.defaultUiLanguage.help")}</p>
          </div>

          <div className="max-w-sm space-y-2">
            <div className="flex items-center gap-2">
              <Label htmlFor="chat_response_language">{t("settings.aiChat.chatResponseLanguage.label")}</Label>
              {languageSaveStatus === "saving" && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
              {languageSaveStatus === "saved" && <Check className="h-3.5 w-3.5 text-emerald-500" />}
            </div>
            <Select
              id="chat_response_language"
              value={form.chat_response_language}
              onChange={(e) => saveLanguageField("chat_response_language", e.target.value)}
            >
              {CHAT_RESPONSE_LANGUAGES.map((lang) => (
                <option key={lang.value} value={lang.value}>
                  {lang.label}
                </option>
              ))}
            </Select>
          </div>
          {languageSaveError && <p className="text-sm text-destructive">{languageSaveError}</p>}
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
              {TIMEZONE_OPTIONS.map(({ tz, label }) => (
                <option key={tz} value={tz}>
                  {label}
                </option>
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
