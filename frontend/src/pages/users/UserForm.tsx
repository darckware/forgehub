import { useState } from "react";
import { Loader2, Save, Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { AuthUser } from "@/store/authStore";
import { useCreateUser, useUpdateUser, useProfiles } from "@/hooks/useAuth";
import { useTranslation } from "react-i18next";

interface Props {
  user?: AuthUser;
  onClose: () => void;
}

function PasswordInput({
  value,
  onChange,
  required,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  placeholder?: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <Input
        type={show ? "text" : "password"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        placeholder={placeholder}
        className="pr-9"
      />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
        tabIndex={-1}
      >
        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
}

export default function UserForm({ user, onClose }: Props) {
  const { t } = useTranslation("users");
  const [username, setUsername] = useState(user?.username ?? "");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [email, setEmail] = useState(user?.email ?? "");
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [isAdmin, setIsAdmin] = useState(user?.is_admin ?? false);
  const [isActive, setIsActive] = useState(user?.is_active ?? true);
  const [profileId, setProfileId] = useState(user?.profile_id ?? "");

  const { data: profiles } = useProfiles();
  const createMut = useCreateUser();
  const updateMut = useUpdateUser();
  const isPending = createMut.isPending || updateMut.isPending;
  const error = createMut.error ?? updateMut.error;

  const passwordRequired = !user;
  const passwordFilled = password.length > 0;
  const confirmMismatch = passwordFilled && confirm !== password;
  const canSubmit = !isPending && (!passwordFilled || !confirmMismatch);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (confirmMismatch) return;
    try {
      if (user) {
        await updateMut.mutateAsync({
          id: user.id,
          body: {
            ...(passwordFilled ? { password } : {}),
            email: email || undefined,
            full_name: fullName || undefined,
            is_admin: isAdmin,
            is_active: isActive,
            profile_id: profileId || null,
          },
        });
      } else {
        await createMut.mutateAsync({
          username,
          password,
          email: email || undefined,
          full_name: fullName || undefined,
          is_admin: isAdmin,
          profile_id: profileId || undefined,
        });
      }
      onClose();
    } catch {
      // shown below
    }
  };

  return (
    <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-3">
      {!user && (
        <div className="flex flex-col gap-1">
          <Label>{t("users.form.usernameLabel")}</Label>
          <Input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            placeholder={t("users.form.usernamePlaceholder")}
          />
        </div>
      )}

      <div className="flex flex-col gap-1">
        <Label>{user ? t("users.form.newPassword") : t("users.form.passwordLabel")}</Label>
        <PasswordInput
          value={password}
          onChange={setPassword}
          required={passwordRequired}
          placeholder={user ? t("users.form.leaveBlank") : t("users.form.passwordPlaceholder")}
        />
      </div>

      <div className="flex flex-col gap-1">
        <Label>
          {t("users.form.confirmLabel")}
          {!passwordRequired && !passwordFilled && (
            <span className="ml-1 text-muted-foreground font-normal text-xs">({t("users.form.optional")})</span>
          )}
        </Label>
        <PasswordInput
          value={confirm}
          onChange={setConfirm}
          required={passwordRequired || passwordFilled}
          placeholder={t("users.form.confirmPlaceholder")}
        />
        {confirmMismatch && (
          <p className="text-xs text-destructive">{t("users.form.passwordsMismatch")}</p>
        )}
      </div>

      <div className="flex flex-col gap-1">
        <Label>{t("users.form.fullNameLabel")}</Label>
        <Input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder={t("users.form.fullNamePlaceholder")} />
      </div>

      <div className="flex flex-col gap-1">
        <Label>{t("users.form.emailLabel")}</Label>
        <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("users.form.emailPlaceholder")} />
      </div>

      <div className="flex items-center gap-4 col-span-2">
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={isAdmin}
            onChange={(e) => {
              setIsAdmin(e.target.checked);
              if (e.target.checked) setProfileId("");
            }}
            className="h-4 w-4 rounded border-border"
          />
          <span className="text-sm font-medium">{t("users.form.superAdminLabel")}</span>
        </label>
        <span className="text-xs text-muted-foreground">{t("users.form.superAdminDesc")}</span>
        {user && (
          <label className="flex items-center gap-2 cursor-pointer select-none ml-4">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="h-4 w-4 rounded border-border"
            />
            <span className="text-sm">{t("users.form.activeLabel")}</span>
          </label>
        )}
      </div>

      {!isAdmin && (
        <div className="flex flex-col gap-1 col-span-2">
          <Label>Access Profile</Label>
          <select
            value={profileId}
            onChange={(e) => setProfileId(e.target.value)}
            className="flex h-9 w-full rounded-md border border-input px-3 py-1 text-sm shadow-sm text-foreground"
            style={{ backgroundColor: "hsl(var(--background))" }}
          >
            <option value="">— no profile —</option>
            {profiles?.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
      )}

      {error && <p className="col-span-2 text-xs text-destructive">{error.message}</p>}

      <div className="col-span-2 flex gap-2 justify-end">
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
        <Button type="submit" size="sm" disabled={!canSubmit} className="gap-1.5">
          {isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
          Save
        </Button>
      </div>
    </form>
  );
}
