import { useTranslation } from "react-i18next";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { serverFormSchema } from "@/hooks/useServers";

export function isValidSshPort(value: string): boolean {
  return serverFormSchema.shape.ssh_port.safeParse(Number(value)).success;
}

/** Shared by the workstation preparation and server key installation dialogs. */
export function SshPortField({ id, value, onChange, disabled }: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation("remoteAccess", { keyPrefix: "servers.form" });
  const invalid = !isValidSshPort(value);
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{t("sshPort")}</Label>
      <Input id={id} type="number" min={1} max={65535} step={1} value={value}
        onChange={(event) => onChange(event.target.value)} disabled={disabled}
        aria-invalid={invalid} aria-describedby={invalid ? `${id}-error` : undefined}
        className="font-mono max-md:text-base" />
      {invalid && <p id={`${id}-error`} role="alert" className="text-xs text-destructive">{t("invalidSshPort")}</p>}
    </div>
  );
}
