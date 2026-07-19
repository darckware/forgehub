import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FileText, Loader2, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  PROFILE_MARKDOWN_FILES,
  useProfileFile,
  useUpdateProfileFile,
  type ProfileMarkdownFile,
} from "@/hooks/useFoundation";

// Maps each profile Markdown filename to its translation key under
// "profileFiles.tabs" — the filenames themselves are literal and never translated.
const TAB_LABEL_KEYS: Record<ProfileMarkdownFile, string> = {
  "SOUL.md": "soul",
  "MEMORY.md": "memory",
  "TOOLS.md": "tools",
  "AGENTS.md": "agents",
  "HEARTBEAT.md": "heartbeat",
  "USER.md": "user",
};

function ProfileFileEditor({
  profileSlug,
  filename,
}: {
  profileSlug: string;
  filename: ProfileMarkdownFile;
}) {
  const { t } = useTranslation("agent");
  const { data, isLoading, isError, error } = useProfileFile(profileSlug, filename);
  const updateFile = useUpdateProfileFile(profileSlug, filename);
  const [draft, setDraft] = useState<string | null>(null);

  const savedContent = data?.content ?? "";
  const content = draft ?? savedContent;
  const isDirty = draft !== null && draft !== savedContent;

  function handleSave() {
    updateFile.mutate(content, {
      onSuccess: () => setDraft(null),
    });
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t("profileFiles.loading", { filename })}
      </div>
    );
  }

  if (isError) {
    return (
      <p className="py-4 text-sm text-destructive">
        {t("profileFiles.loadError", { filename, message: (error as Error)?.message })}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {data?.content === null && (
        <p className="text-sm italic text-muted-foreground">
          {t("profileFiles.fileMissing", { filename })}
        </p>
      )}
      <Textarea
        value={content}
        onChange={(e) => setDraft(e.target.value)}
        rows={16}
        className="font-mono text-xs"
        placeholder={`# ${filename}`}
      />
      <div className="flex items-center justify-end gap-3">
        {updateFile.isError && (
          <p className="text-sm text-destructive">
            {t("profileFiles.saveError", { message: (updateFile.error as Error)?.message })}
          </p>
        )}
        {updateFile.isSuccess && !isDirty && (
          <p className="text-sm text-muted-foreground">{t("profileFiles.saved")}</p>
        )}
        <Button onClick={handleSave} disabled={!isDirty || updateFile.isPending} size="sm">
          {updateFile.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Save className="mr-2 h-4 w-4" />
          )}
          {t("profileFiles.saveButton")}
        </Button>
      </div>
    </div>
  );
}

export function ProfileFilesCard({ profileSlug }: { profileSlug: string }) {
  const { t } = useTranslation("agent");
  const [activeTab, setActiveTab] = useState<ProfileMarkdownFile>("SOUL.md");

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-xl">
          <FileText className="h-5 w-5" />
          {t("profileFiles.title")}
        </CardTitle>
        <CardDescription>
          {t("profileFiles.description")} (
          <code>/root/.hermes/profiles/{profileSlug}/</code>).
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as ProfileMarkdownFile)}>
          <TabsList>
            {PROFILE_MARKDOWN_FILES.map((file) => (
              <TabsTrigger key={file} value={file}>
                {t(`profileFiles.tabs.${TAB_LABEL_KEYS[file]}`)}
              </TabsTrigger>
            ))}
          </TabsList>
          {PROFILE_MARKDOWN_FILES.map((file) => (
            <TabsContent key={file} value={file} className="mt-4">
              <ProfileFileEditor profileSlug={profileSlug} filename={file} />
            </TabsContent>
          ))}
        </Tabs>
      </CardContent>
    </Card>
  );
}
