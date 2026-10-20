import { useTranslation } from "react-i18next";
import { useUpdateMe } from "@/hooks/useAuth";
import { SUPPORTED_UI_LANGUAGES, UI_LANGUAGE_OPTIONS, type UiLanguage } from "@/i18n";
import { useAuthStore } from "@/store/authStore";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";

export function MyLanguageControl() {
  const { t } = useTranslation("settings");
  const savedLanguage = useAuthStore((state) => state.user?.ui_language);
  const updateMe = useUpdateMe();
  const value = SUPPORTED_UI_LANGUAGES.includes(savedLanguage as UiLanguage)
    ? savedLanguage
    : "pt-BR";

  return (
    <div className="max-w-sm space-y-2">
      <Label htmlFor="my_ui_language">{t("settings.aiChat.myUiLanguage.label")}</Label>
      <Select
        id="my_ui_language"
        value={value}
        disabled={updateMe.isPending}
        onChange={(event) => updateMe.mutate({ ui_language: event.target.value as UiLanguage })}
      >
        {UI_LANGUAGE_OPTIONS.map((language) => (
          <option key={language.value} value={language.value}>{language.label}</option>
        ))}
      </Select>
      <p className="text-sm text-muted-foreground">{t("settings.aiChat.myUiLanguage.help")}</p>
      {updateMe.isError && (
        <p role="alert" className="text-sm text-destructive">
          {t("settings.aiChat.myUiLanguage.saveError")}
        </p>
      )}
    </div>
  );
}
