import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { AuthUser } from "@/store/authStore";
import { useCreateUser, useUpdateUser, useProfiles } from "@/hooks/useAuth";
import { useTranslation } from "react-i18next";

const schema = z.object({
  username: z.string().trim().min(1).max(100), password: z.string(), confirm: z.string(),
  email: z.union([z.literal(""), z.string().email()]), full_name: z.string(), phone: z.string().max(255),
  job_title: z.string().max(255), department: z.string().max(255), profile_id: z.string(),
  is_admin: z.boolean(), is_active: z.boolean(),
}).refine(v => v.password === v.confirm, { path: ["confirm"] });
type Values = z.infer<typeof schema>;

export default function UserForm({ user, onClose }: { user?: AuthUser; onClose: () => void }) {
  const { t } = useTranslation("users");
  const { data: profiles } = useProfiles();
  const create = useCreateUser();
  const update = useUpdateUser();
  const [avatar, setAvatar] = useState<string | null>(user?.avatar_data_url ?? null);
  const { register, handleSubmit, watch, formState: { errors } } = useForm<Values>({
    resolver: zodResolver(schema), defaultValues: {
      username: user?.username ?? "", password: "", confirm: "", email: user?.email ?? "",
      full_name: user?.full_name ?? "", phone: user?.phone ?? "", job_title: user?.job_title ?? "",
      department: user?.department ?? "", profile_id: user?.profile_id ?? "",
      is_admin: user?.is_admin ?? false, is_active: user?.is_active ?? true,
    },
  });
  const [missingPassword, setMissingPassword] = useState(false);
  const pending = create.isPending || update.isPending;
  const onSubmit = handleSubmit(async values => {
    if (!user && !values.password) { setMissingPassword(true); return; }
    const { confirm: _confirm, password, profile_id, ...rest } = values;
    try {
      if (user) await update.mutateAsync({ id: user.id, body: { ...rest, password: password || undefined, profile_id: values.is_admin ? null : profile_id || null, avatar_data_url: avatar } });
      else await create.mutateAsync({ ...rest, password, profile_id: values.is_admin ? undefined : profile_id || undefined, avatar_data_url: avatar });
      onClose();
    } catch { /* mutation error is shown below */ }
  });
  return <form onSubmit={onSubmit} noValidate className="grid grid-cols-1 sm:grid-cols-2 gap-3">
    <div className="flex flex-col gap-1"><Label htmlFor="user-photo">{t("users.form.photo")}</Label>
      {avatar && <img src={avatar} alt="" className="h-16 w-16 rounded-full object-cover" />}
      <Input id="user-photo" type="file" accept="image/*" onChange={e => { const file = e.target.files?.[0]; if (file) { const reader = new FileReader(); reader.onload = () => setAvatar(String(reader.result)); reader.readAsDataURL(file); } }} />
    </div>
    {(["username", "full_name", "email", "phone", "job_title", "department"] as const).map(field => <div className="flex flex-col gap-1" key={field}>
      <Label htmlFor={`user-${field}`}>{t(`users.form.fields.${field}`)}</Label>
      <Input id={`user-${field}`} type={field === "email" ? "email" : "text"} {...register(field)} />
      {errors[field] && <span className="text-xs text-destructive">{t("users.form.invalid")}</span>}
    </div>)}
    {(["password", "confirm"] as const).map(field => <div className="flex flex-col gap-1" key={field}>
      <Label htmlFor={`user-${field}`}>{field === "password" ? (user ? t("users.form.newPassword") : t("users.form.passwordLabel")) : t("users.form.confirmLabel")}</Label>
      <Input id={`user-${field}`} type="password" {...register(field)} />
      {(errors[field] || (field === "password" && missingPassword)) && <span className="text-xs text-destructive">{t(field === "confirm" ? "users.form.passwordsMismatch" : "users.form.invalid")}</span>}
    </div>)}
    <label className="flex items-center gap-2"><input type="checkbox" {...register("is_admin")} />{t("users.form.superAdminLabel")}</label>
    <label className="flex items-center gap-2"><input type="checkbox" {...register("is_active")} />{t("users.form.activeLabel")}</label>
    {!watch("is_admin") && <div className="flex flex-col gap-1"><Label htmlFor="user-profile">{t("users.form.profileLabel")}</Label>
      <select id="user-profile" {...register("profile_id")} className="h-9 rounded-md border bg-background px-3 text-sm"><option value="">{t("users.form.profilePlaceholder")}</option>{profiles?.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
    </div>}
    {user && <div className="text-sm">{t("users.form.twoFactor")}: {t(user.totp_enabled ? "users.status.active" : "users.status.inactive")}</div>}
    {(create.error || update.error) && <p role="alert" className="text-xs text-destructive sm:col-span-2">{(create.error || update.error)?.message}</p>}
    <div className="flex justify-end gap-2 sm:col-span-2"><Button type="button" variant="ghost" onClick={onClose}>{t("users.form.cancel")}</Button>
      <Button type="submit" disabled={pending}>{pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} {t("users.form.save")}</Button></div>
  </form>;
}
