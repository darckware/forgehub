import { useEffect, useId, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Camera, Check, ExternalLink, Info, KeyRound, Laptop, LogOut, Loader2, Moon, Settings, Settings2, ShieldCheck, Sun, User as UserIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api";
import { useClickOutside } from "@/hooks/useClickOutside";
import { useTheme } from "@/lib/theme";
import type { UiLanguage } from "@/i18n";
import { useAuthStore } from "@/store/authStore";
import { useUpdateMe, useChangeMyPassword, useClearQueryCacheOnLogout } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { TwoFactorModal } from "./TwoFactorModal";

const THEME_OPTIONS = [
  { value: "light" as const, labelKey: "themeLight", icon: Sun },
  { value: "dark" as const, labelKey: "themeDark", icon: Moon },
  { value: "system" as const, labelKey: "themeSystem", icon: Laptop },
];

const LANGUAGE_OPTIONS: { value: UiLanguage; labelKey: string }[] = [
  { value: "pt-BR", labelKey: "languagePt" },
  { value: "en", labelKey: "languageEn" },
  { value: "es", labelKey: "languageEs" },
];

/** Backdrop + centered panel, same pattern as components/ui/confirm-dialog.tsx. */
function ModalShell({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    panelRef.current
      ?.querySelector<HTMLElement>("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])")
      ?.focus();
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      onKeyDown={(event) => {
        if (event.key === "Escape") onClose();
      }}
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div ref={panelRef} className="relative z-10 w-full max-w-sm rounded-xl border border-border bg-card p-6 shadow-2xl">
        <h2 id={titleId} className="mb-4 text-base font-semibold">{title}</h2>
        {children}
      </div>
    </div>
  );
}

interface SystemVersion {
  app_version: string;
  git_sha: string;
  git_commit_url: string | null;
  build_date: string;
  postgres_version: string | null;
  latest_migration_bundled: string | null;
  github_repo_url: string;
}

function AboutModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation("common");
  const version = useQuery({
    queryKey: ["system-version"],
    queryFn: () => apiClient.get<SystemVersion>("/api/v1/system/version"),
  });

  return (
    <ModalShell title={t("userMenu.about")} onClose={onClose}>
      {version.isPending && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t("userMenu.versionLoading")}
        </div>
      )}
      {version.isError && (
        <p className="text-sm text-destructive" role="alert">
          {t("userMenu.versionError")}
        </p>
      )}
      {version.data && (
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm">
          <dt className="text-muted-foreground">{t("userMenu.appVersion")}</dt>
          <dd className="font-mono">{version.data.app_version}</dd>
          <dt className="text-muted-foreground">{t("userMenu.gitCommit")}</dt>
          <dd className="min-w-0 break-all font-mono">
            {version.data.git_commit_url ? (
              <a className="inline-flex items-center gap-1 text-primary hover:underline" href={version.data.git_commit_url} target="_blank" rel="noreferrer">
                {version.data.git_sha}<ExternalLink className="h-3 w-3" />
              </a>
            ) : version.data.git_sha}
          </dd>
          <dt className="text-muted-foreground">{t("userMenu.buildDate")}</dt>
          <dd className="break-all font-mono text-xs">{version.data.build_date}</dd>
          <dt className="text-muted-foreground">PostgreSQL</dt>
          <dd className="break-words text-xs">{version.data.postgres_version ?? t("userMenu.unavailable")}</dd>
          <dt className="text-muted-foreground">{t("userMenu.migration")}</dt>
          <dd className="break-all font-mono text-xs">{version.data.latest_migration_bundled ?? t("userMenu.unavailable")}</dd>
          <dt className="text-muted-foreground">{t("userMenu.repository")}</dt>
          <dd>
            <a className="inline-flex items-center gap-1 text-primary hover:underline" href={version.data.github_repo_url} target="_blank" rel="noreferrer">
              GitHub<ExternalLink className="h-3 w-3" />
            </a>
          </dd>
        </dl>
      )}
      <div className="mt-5 flex justify-end">
        <Button variant="outline" size="sm" onClick={onClose}>{t("userMenu.close")}</Button>
      </div>
    </ModalShell>
  );
}

function AccountModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation("common");
  const user = useAuthStore((s) => s.user);
  const updateMe = useUpdateMe();
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [avatarPreview, setAvatarPreview] = useState<string | null>(user?.avatar_data_url ?? null);
  // Staged like fullName/email above -- previously this field applied
  // (i18n.changeLanguage) and persisted (mutate) directly in its onChange,
  // bypassing Cancel entirely (picking a language then hitting Cancel still
  // left you on the new language). Now it only takes effect on Save, same
  // as every other field in this modal.
  const [uiLanguage, setUiLanguage] = useState<UiLanguage>((user?.ui_language as UiLanguage) ?? "pt-BR");
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handlePickPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setAvatarPreview(reader.result as string);
    reader.readAsDataURL(file);
  }

  function handleSave() {
    updateMe.mutate(
      {
        full_name: fullName.trim() || undefined,
        email: email.trim() || undefined,
        avatar_data_url: avatarPreview,
        ui_language: uiLanguage,
      },
      { onSuccess: onClose }
    );
    // No explicit i18n.changeLanguage here -- useUpdateMe's onSuccess writes
    // the fresh user (including ui_language) into authStore, and
    // useSyncUiLanguage (mounted once in AppLayout) reactively applies it
    // app-wide the moment that store value changes.
  }

  return (
    <ModalShell title={t("userMenu.account")} onClose={onClose}>
      <div className="space-y-4">
        <div className="flex justify-center">
          <button
            type="button"
            className="group relative h-16 w-16 shrink-0 overflow-hidden rounded-full bg-accent"
            onClick={() => fileInputRef.current?.click()}
            aria-label={t("userMenu.changeUserPhoto")}
            title={t("userMenu.changePhoto")}
          >
            {avatarPreview ? (
              <img src={avatarPreview} alt="" className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center text-lg font-bold uppercase text-accent-foreground">
                {user?.username?.[0]}
              </div>
            )}
            <div className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 transition-opacity group-hover:opacity-100">
              <Camera className="h-5 w-5 text-white" />
            </div>
          </button>
          <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={handlePickPhoto} />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">{t("userMenu.username")}</label>
          <p className="text-sm">{user?.username}</p>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">{t("userMenu.fullName")}</label>
          <input
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="h-9 w-full rounded-md border border-border bg-transparent px-3 text-sm outline-none focus:border-primary"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">{t("userMenu.email")}</label>
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="h-9 w-full rounded-md border border-border bg-transparent px-3 text-sm outline-none focus:border-primary"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">{t("userMenu.language")}</label>
          <select
            value={uiLanguage}
            onChange={(e) => setUiLanguage(e.target.value as UiLanguage)}
            className="h-9 w-full rounded-md border border-border bg-transparent px-3 text-sm outline-none focus:border-primary"
          >
            {LANGUAGE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {t(`userMenu.${opt.labelKey}`)}
              </option>
            ))}
          </select>
        </div>
        {updateMe.isError && (
          <p className="text-xs text-destructive">{t("userMenu.saveError")}</p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" size="sm" onClick={onClose}>
            {t("userMenu.cancel")}
          </Button>
          <Button size="sm" onClick={handleSave} disabled={updateMe.isPending}>
            {updateMe.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
            {t("userMenu.save")}
          </Button>
        </div>
      </div>
    </ModalShell>
  );
}

function ChangePasswordModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation("common");
  const changePassword = useChangeMyPassword();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  function handleSave() {
    setLocalError(null);
    if (newPassword.length < 8) {
      setLocalError(t("userMenu.passwordTooShort"));
      return;
    }
    if (newPassword !== confirmPassword) {
      setLocalError(t("userMenu.passwordsDoNotMatch"));
      return;
    }
    changePassword.mutate(
      { current_password: currentPassword, new_password: newPassword },
      { onSuccess: onClose }
    );
  }

  return (
    <ModalShell title={t("userMenu.changePassword")} onClose={onClose}>
      <div className="space-y-4">
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">{t("userMenu.currentPassword")}</label>
          <input
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            className="h-9 w-full rounded-md border border-border bg-transparent px-3 text-sm outline-none focus:border-primary"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">{t("userMenu.newPassword")}</label>
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="h-9 w-full rounded-md border border-border bg-transparent px-3 text-sm outline-none focus:border-primary"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">{t("userMenu.confirmNewPassword")}</label>
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className="h-9 w-full rounded-md border border-border bg-transparent px-3 text-sm outline-none focus:border-primary"
          />
        </div>
        {(localError || changePassword.isError) && (
          <p className="text-xs text-destructive">
            {localError ?? t("userMenu.currentPasswordIncorrect")}
          </p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" size="sm" onClick={onClose}>
            {t("userMenu.cancel")}
          </Button>
          <Button size="sm" onClick={handleSave} disabled={changePassword.isPending}>
            {changePassword.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
            {t("userMenu.save")}
          </Button>
        </div>
      </div>
    </ModalShell>
  );
}

/** Gear icon + dropdown (Account / Change password / Theme / Log out) --
 * replaces the standalone ThemeToggle and the standalone "Log out" button
 * that used to sit in the sidebar header/footer, folding all
 * account-adjacent actions into this single settings menu instead.
 * Language lives inside the Account modal (a persisted profile field, same
 * PATCH /users/me as name/email), not here -- this quick dropdown is for
 * per-device/session toggles (Theme) and navigation, not profile edits.
 *
 * `collapsed` controls icon-only vs icon+label. `stretch` controls whether
 * the trigger fills its container's width (the standalone rail-mode
 * button) or sits at its own intrinsic size (embedded inline next to the
 * username, right-aligned via the parent's flex row). */
export function UserSettingsMenu({
  collapsed,
  stretch = true,
  avatarUrl,
  usernameInitial,
  avatarTrigger = false,
}: {
  collapsed: boolean;
  stretch?: boolean;
  /** Rail-mode (collapsed && stretch) or avatarTrigger: shows the user's
   * photo (or initial) as the trigger instead of the gear icon. */
  avatarUrl?: string | null;
  usernameInitial?: string;
  /** Forces the avatar-photo trigger even outside rail mode -- used
   * inline in the expanded user row, where the avatar itself opens the
   * Account/Password/Theme dropdown instead of a separate gear button. */
  avatarTrigger?: boolean;
}) {
  const { t } = useTranslation("common");
  const [open, setOpen] = useState(false);
  const [modal, setModal] = useState<"account" | "password" | "twofactor" | "about" | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  useClickOutside(containerRef, () => setOpen(false), open);
  const { theme, setTheme } = useTheme();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const clearAuth = useAuthStore((s) => s.clearAuth);
  const clearQueryCache = useClearQueryCacheOnLogout();

  function handleLogout() {
    setOpen(false);
    clearQueryCache();
    clearAuth();
    navigate("/login", { replace: true });
  }

  const railMode = collapsed && stretch;
  const showAvatar = railMode || avatarTrigger;

  return (
    <>
      <div className={cn("relative", stretch && "w-full")} ref={containerRef}>
        <Button
          variant="ghost"
          size={collapsed || avatarTrigger ? "icon" : "default"}
          className={cn(
            "text-muted-foreground",
            stretch && "w-full",
            !collapsed && !avatarTrigger && "justify-start gap-3",
            avatarTrigger && "h-7 w-7 rounded-full p-0"
          )}
          aria-label={t("userMenu.settings")}
          title={t("userMenu.settings")}
          onClick={() => setOpen((v) => !v)}
        >
          {showAvatar ? (
            <span
              className={cn(
                "flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-accent font-bold uppercase text-accent-foreground",
                avatarTrigger ? "h-7 w-7 text-xs" : "h-6 w-6 text-[11px]"
              )}
            >
              {avatarUrl ? (
                <img src={avatarUrl} alt="" className="h-full w-full object-cover" />
              ) : (
                usernameInitial
              )}
            </span>
          ) : (
            <Settings className="h-4 w-4 shrink-0" />
          )}
          {!collapsed && !avatarTrigger && t("userMenu.settings")}
        </Button>
        {open && (
          <div
            className="absolute bottom-0 left-full z-20 ml-1 w-48 overflow-hidden rounded-md border border-border bg-card py-1 shadow-md"
          >
            <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
              {t("userMenu.account")}
            </p>
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
              onClick={() => {
                setModal("account");
                setOpen(false);
              }}
            >
              <UserIcon className="h-3.5 w-3.5" />
              {t("userMenu.account")}
            </button>
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
              onClick={() => {
                setModal("password");
                setOpen(false);
              }}
            >
              <KeyRound className="h-3.5 w-3.5" />
              {t("userMenu.changePassword")}
            </button>
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
              onClick={() => {
                setModal("twofactor");
                setOpen(false);
              }}
            >
              <ShieldCheck className="h-3.5 w-3.5" />
              {t("userMenu.twoFactor")}
            </button>
            {user?.is_admin && (
              <button
                type="button"
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
                onClick={() => {
                  setOpen(false);
                  navigate("/settings");
                }}
              >
                <Settings2 className="h-3.5 w-3.5" />
                {t("userMenu.systemSettings")}
              </button>
            )}
            <div className="my-1 border-t border-border" />
            <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
              {t("userMenu.theme")}
            </p>
            {THEME_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
                onClick={() => setTheme(opt.value)}
              >
                <opt.icon className="h-3.5 w-3.5" />
                <span className="flex-1">{t(`userMenu.${opt.labelKey}`)}</span>
                {theme === opt.value && <Check className="h-3.5 w-3.5" />}
              </button>
            ))}
            <div className="my-1 border-t border-border" />
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
              onClick={() => {
                setModal("about");
                setOpen(false);
              }}
            >
              <Info className="h-3.5 w-3.5" />
              {t("userMenu.about")}
            </button>
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              onClick={handleLogout}
            >
              <LogOut className="h-3.5 w-3.5" />
              {t("userMenu.logout")}
            </button>
          </div>
        )}
      </div>
      {modal === "account" && <AccountModal onClose={() => setModal(null)} />}
      {modal === "password" && <ChangePasswordModal onClose={() => setModal(null)} />}
      {modal === "twofactor" && <TwoFactorModal onClose={() => setModal(null)} />}
      {modal === "about" && <AboutModal onClose={() => setModal(null)} />}
    </>
  );
}
