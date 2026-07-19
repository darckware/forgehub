import { useState } from "react";
import { Loader2, Plus, Pencil, Trash2, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useProfiles, useDeleteProfile } from "@/hooks/useAuth";
import ProfileForm from "./ProfileForm";
import { useTranslation } from "react-i18next";

export default function ProfilesPage() {
  const { t } = useTranslation("profiles");
  const { data: profiles, isLoading } = useProfiles();
  const deleteMut = useDeleteProfile();
  const [editing, setEditing] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(t("profiles.delete.confirm", { name }))) return;
    await deleteMut.mutateAsync(id);
  };

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <ShieldCheck className="h-5 w-5" /> {t("profiles.list.title")}
        </h1>
        <Button size="sm" className="gap-1.5" onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4" /> {t("profiles.list.create")}
        </Button>
      </div>

      {creating && <ProfileForm onClose={() => setCreating(false)} />}

      {isLoading && (
        <div className="flex justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}

      {profiles?.map((profile) => (
        <Card key={profile.id}>
          <CardContent className="p-0">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <div>
                <p className="font-medium">{profile.name}</p>
                {profile.description && (
                  <p className="text-xs text-muted-foreground">{profile.description}</p>
                )}
              </div>
              <div className="flex gap-1">
                <Button
                  size="icon" variant="ghost" className="h-7 w-7"
                  onClick={() => setEditing(editing === profile.id ? null : profile.id)}
                  title="Edit"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
                <Button
                  size="icon" variant="ghost" className="h-7 w-7 text-destructive hover:text-destructive"
                  onClick={() => handleDelete(profile.id, profile.name)}
                  disabled={deleteMut.isPending}
                  title="Delete"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>

            {editing === profile.id && (
              <div className="px-4 py-3 bg-muted/10">
                <ProfileForm profile={profile} onClose={() => setEditing(null)} />
              </div>
            )}

            {/* Permissions matrix — hidden while edit form is open */}
            {editing !== profile.id && <div className="overflow-x-auto overflow-y-auto max-h-48">
              <table className="w-full text-xs">
                <thead>
                  <tr className="sticky top-0 z-10 border-b border-border/50">
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground w-40" style={{ backgroundColor: "hsl(var(--card))" }}>{t("profiles.permissions.column.module")}</th>
                    <th className="px-3 py-2 text-center font-medium text-muted-foreground" style={{ backgroundColor: "hsl(var(--card))" }}>{t("profiles.permissions.column.view")}</th>
                    <th className="px-3 py-2 text-center font-medium text-muted-foreground" style={{ backgroundColor: "hsl(var(--card))" }}>{t("profiles.permissions.column.query")}</th>
                    <th className="px-3 py-2 text-center font-medium text-muted-foreground" style={{ backgroundColor: "hsl(var(--card))" }}>{t("profiles.permissions.column.write")}</th>
                    <th className="px-3 py-2 text-center font-medium text-muted-foreground" style={{ backgroundColor: "hsl(var(--card))" }}>{t("profiles.permissions.column.delete")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/30">
                  {profile.permissions.map((perm) => (
                    <tr key={perm.module} className="hover:bg-muted/20">
                      <td className="px-3 py-1.5 font-mono">{perm.module}</td>
                      <td className="px-3 py-1.5 text-center">{perm.can_view ? "✓" : "—"}</td>
                      <td className="px-3 py-1.5 text-center">{perm.can_query ? "✓" : "—"}</td>
                      <td className="px-3 py-1.5 text-center">{perm.can_write ? "✓" : "—"}</td>
                      <td className="px-3 py-1.5 text-center">{perm.can_delete ? "✓" : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
