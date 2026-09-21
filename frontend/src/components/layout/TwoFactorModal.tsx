import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Check, Loader2, ShieldCheck, ShieldOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { OtpInput, OTP_LENGTH } from "@/components/ui/otp-input";
import { useAuthStore } from "@/store/authStore";
import { useSetupTotp, useEnableTotp, useDisableTotp } from "@/hooks/useAuth";

function ModalShell({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-2xl">
        <h2 className="mb-4 text-base font-semibold">{title}</h2>
        {children}
      </div>
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="ml-2 text-muted-foreground hover:text-foreground transition-colors"
      onClick={() => {
        void navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
      title="Copy"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-green-500" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  );
}

export function TwoFactorModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation("common");
  const user = useAuthStore((s) => s.user);
  const isEnabled = user?.totp_enabled ?? false;

  const setupTotp = useSetupTotp();
  const enableTotp = useEnableTotp();
  const disableTotp = useDisableTotp();

  const [step, setStep] = useState<"idle" | "setup" | "verify" | "disable">("idle");
  const [secret, setSecret] = useState("");
  const [qrCodeUrl, setQrCodeUrl] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");

  async function handleSetup() {
    try {
      const data = await setupTotp.mutateAsync();
      setSecret(data.secret);
      setQrCodeUrl(data.qr_code_data_url);
      setRecoveryCodes(data.recovery_codes);
      setStep("setup");
    } catch {
      // error shown via setupTotp.error
    }
  }

  async function handleEnable() {
    try {
      await enableTotp.mutateAsync({ secret, code, recovery_codes: recoveryCodes });
      setStep("idle");
      setCode("");
    } catch {
      // error shown via enableTotp.error
    }
  }

  async function handleDisable() {
    try {
      await disableTotp.mutateAsync({ password, code });
      setStep("idle");
      setCode("");
      setPassword("");
    } catch {
      // error shown via disableTotp.error
    }
  }

  return (
    <ModalShell title={t("userMenu.twoFactor")} onClose={onClose}>
      {step === "idle" && !isEnabled && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            {t("userMenu.twoFactorDescription")}
          </p>
          {setupTotp.isError && (
            <p className="text-xs text-destructive">{t("userMenu.twoFactorSetupError")}</p>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={onClose}>{t("userMenu.cancel")}</Button>
            <Button size="sm" onClick={handleSetup} disabled={setupTotp.isPending}>
              {setupTotp.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
              {t("userMenu.twoFactorSetup")}
            </Button>
          </div>
        </div>
      )}

      {step === "idle" && isEnabled && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-sm text-green-500">
            <ShieldCheck className="h-4 w-4" />
            {t("userMenu.twoFactorActive")}
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={onClose}>{t("userMenu.close")}</Button>
            <Button variant="destructive" size="sm" onClick={() => setStep("disable")}>
              <ShieldOff className="mr-1.5 h-3.5 w-3.5" />
              {t("userMenu.twoFactorDisable")}
            </Button>
          </div>
        </div>
      )}

      {step === "setup" && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">{t("userMenu.twoFactorScanQr")}</p>
          <div className="flex justify-center">
            <img src={qrCodeUrl} alt="TOTP QR Code" className="h-48 w-48 rounded border border-border" />
          </div>
          <div className="rounded border border-border bg-muted/50 p-3">
            <p className="mb-1 text-xs font-medium text-muted-foreground">{t("userMenu.twoFactorManualKey")}</p>
            <div className="flex items-center">
              <code className="flex-1 break-all font-mono text-xs">{secret}</code>
              <CopyButton text={secret} />
            </div>
          </div>
          <div className="rounded border border-border bg-muted/50 p-3">
            <div className="mb-1 flex items-center justify-between">
              <p className="text-xs font-medium text-muted-foreground">{t("userMenu.twoFactorRecoveryCodes")}</p>
              <CopyButton text={recoveryCodes.join("\n")} />
            </div>
            <p className="mb-2 text-xs text-muted-foreground/70">{t("userMenu.twoFactorRecoveryWarning")}</p>
            <div className="grid grid-cols-2 gap-1">
              {recoveryCodes.map((c) => (
                <code key={c} className="rounded bg-muted px-2 py-0.5 font-mono text-xs">{c}</code>
              ))}
            </div>
          </div>
          <Button className="w-full" onClick={() => setStep("verify")}>
            {t("userMenu.twoFactorContinue")}
          </Button>
        </div>
      )}

      {step === "verify" && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground text-center">{t("userMenu.twoFactorEnterCode")}</p>
          <div className="py-2">
            <OtpInput
              value={code}
              onChange={setCode}
              autoFocus
              disabled={enableTotp.isPending}
            />
          </div>
          {enableTotp.isError && (
            <p className="text-xs text-destructive text-center">{t("userMenu.twoFactorInvalidCode")}</p>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => { setStep("setup"); setCode(""); }}>
              {t("userMenu.twoFactorBack")}
            </Button>
            <Button size="sm" onClick={handleEnable} disabled={enableTotp.isPending || code.length !== OTP_LENGTH}>
              {enableTotp.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
              {t("userMenu.twoFactorEnable")}
            </Button>
          </div>
        </div>
      )}

      {step === "disable" && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">{t("userMenu.twoFactorDisableWarning")}</p>
          <div className="space-y-3">
            <input
              autoFocus
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t("userMenu.currentPassword")}
              className="h-9 w-full rounded-md border border-border bg-transparent px-3 text-sm outline-none focus:border-primary"
            />
            <div>
              <p className="mb-2 text-xs text-muted-foreground">{t("userMenu.twoFactorEnterCode")}</p>
              <OtpInput
                value={code}
                onChange={setCode}
                autoFocus={false}
                disabled={disableTotp.isPending}
              />
            </div>
          </div>
          {disableTotp.isError && (
            <p className="text-xs text-destructive text-center">{t("userMenu.twoFactorDisableError")}</p>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => { setStep("idle"); setCode(""); setPassword(""); }}>
              {t("userMenu.cancel")}
            </Button>
            <Button variant="destructive" size="sm" onClick={handleDisable} disabled={disableTotp.isPending || !password || code.length !== OTP_LENGTH}>
              {disableTotp.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
              {t("userMenu.twoFactorDisable")}
            </Button>
          </div>
        </div>
      )}
    </ModalShell>
  );
}
