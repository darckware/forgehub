import { Fragment, useState } from "react";
import { Loader2, Plus, Pencil, Trash2, ShieldCheck, ShieldOff, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useUsers, useDeleteUser, useProfiles } from "@/hooks/useAuth";
import { useAuthStore } from "@/store/authStore";
import UserForm from "./UserForm";
import { useTranslation } from "react-i18next";

export default function UsersPage() {
  const { t } = useTranslation("users");
  const { data: users, isLoading } = useUsers();
  const { data: profiles } = useProfiles();
  const profileMap = Object.fromEntries((profiles ?? []).map((p) => [p.id, p.name]));
  const deleteMut = useDeleteUser();
  const currentUser = useAuthStore((s) => s.user);
  const [editing, setEditing] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const handleDelete = async (id: string, username: string) => {
    if (!confirm(t("users.delete.confirm", { username }))) return;
    await deleteMut.mutateAsync(id);
  };

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <User className="h-5 w-5" /> {t("users.list.title")}
        </h1>
        <Button size="sm" className="gap-1.5" onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4" /> {t("users.list.create")}
        </Button>
      </div>

      {creating && (
        <UserForm onClose={() => setCreating(false)} />
      )}

      {isLoading && (
        <div className="flex justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}

      {users && (
        <Card>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">{t("users.column.user")}</th>
                  <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">{t("users.column.name")}</th>
                  <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">{t("users.column.email")}</th>
                  <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">{t("users.column.role")}</th>
                  <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">{t("users.column.profile")}</th>
                  <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">{t("users.column.status")}</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {users.map((u) => (
                  <Fragment key={u.id}>
                    <tr className="hover:bg-muted/30">
                      <td className="px-4 py-2.5 font-mono font-medium">
                        {u.username}
                        {u.id === currentUser?.id && (
                          <span className="ml-1.5 text-[10px] text-muted-foreground">(you)</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-muted-foreground">{u.full_name ?? "—"}</td>
                      <td className="px-4 py-2.5 text-muted-foreground">{u.email ?? "—"}</td>
                      <td className="px-4 py-2.5">
                        {u.is_admin ? (
                          <Badge variant="outline" className="gap-1 text-amber-600 border-amber-500/30">
                            <ShieldCheck className="h-3 w-3" /> {t("users.badge.admin")}
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="gap-1 text-muted-foreground">
                            <ShieldOff className="h-3 w-3" /> {t("users.badge.user")}
                          </Badge>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-muted-foreground text-sm">
                        {u.is_admin
                          ? <span className="italic text-xs">— {t("users.profile.superAdmin")}</span>
                          : u.profile_id
                            ? profileMap[u.profile_id] ?? <span className="italic text-xs text-muted-foreground/60">{t("users.profile.loading")}</span>
                            : <span className="italic text-xs text-muted-foreground/60">{t("users.profile.none")}</span>
                        }
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge variant={u.is_active ? "outline" : "secondary"}
                          className={u.is_active ? "text-emerald-600 border-emerald-500/30" : ""}>
                          {u.is_active ? t("users.status.active") : t("users.status.inactive")}
                        </Badge>
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-1 justify-end">
                          <Button
                            size="icon" variant="ghost" className="h-7 w-7"
                            onClick={() => setEditing(editing === u.id ? null : u.id)}
                            title={t("users.action.edit")}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          {u.id !== currentUser?.id && (
                            <Button
                              size="icon" variant="ghost" className="h-7 w-7 text-destructive hover:text-destructive"
                              onClick={() => handleDelete(u.id, u.username)}
                              disabled={deleteMut.isPending}
                              title={t("users.action.delete")}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                    {editing === u.id && (
                      <tr key={`edit-${u.id}`}>
                        <td colSpan={7} className="px-4 py-3 bg-muted/10">
                          <UserForm user={u} onClose={() => setEditing(null)} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
