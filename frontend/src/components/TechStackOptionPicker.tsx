import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import {
  TECH_STACK_PLATFORMS, useCreateTechStackOption, useTechStackOptions, type TechStackLayer,
} from "@/hooks/useSystemScope";

const ADD_NEW_VALUE = "__add_new__";

/** Conception step 4 "Tech stack": picks from the org's registered catalog
 * (`tech_stack_options`, seeded from the architecture standard) instead of a
 * free-text Input -- and, unlike a closed enum, "+ Add new option" writes
 * straight into that catalog so it's there for the next concept's picker
 * too. A value carried over from before this picker existed (or a stale
 * revision whose option was later renamed) that doesn't match any catalog
 * row is still rendered as its own selected entry rather than silently
 * dropped -- the field can't lose data just because the catalog moved on. */
export function TechStackOptionPicker({
  layer, value, onChange,
}: {
  layer: TechStackLayer;
  value: string;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation("conception");
  const options = useTechStackOptions(layer);
  const createOption = useCreateTechStackOption();
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState("");

  const list = options.data ?? [];
  const currentIsUnlisted = value.trim().length > 0 && !list.some((option) => option.name === value);
  const selectedDescription = list.find((option) => option.name === value)?.description ?? null;

  function handleSelectChange(raw: string) {
    if (raw === ADD_NEW_VALUE) {
      setDraft("");
      setAdding(true);
      return;
    }
    onChange(raw);
  }

  async function handleConfirmAdd() {
    const name = draft.trim();
    if (!name) return;
    const created = await createOption.mutateAsync({ layer, name });
    onChange(created.name);
    setAdding(false);
    setDraft("");
  }

  if (adding) {
    return (
      <div className="flex items-center gap-2">
        <Input
          autoFocus
          placeholder={t("wizard.stack.newOptionPlaceholder")}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void handleConfirmAdd(); } }}
        />
        <Button type="button" size="sm" onClick={() => void handleConfirmAdd()} disabled={!draft.trim() || createOption.isPending}>
          {createOption.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : t("wizard.stack.confirmAdd")}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={() => { setAdding(false); setDraft(""); }}>
          {t("wizard.stack.cancelAdd")}
        </Button>
      </div>
    );
  }

  // "frontend" mixes several scenarios/toolchains (React+Vite next to plain
  // HTML/CSS next to React Native+Expo) -- split into optgroups there so
  // picking doesn't require reading every option's name to tell which
  // scenario it targets (2026-08-16, Marcelo: "faltou para mobile", then
  // "web app, landing page, site institucional, PWA, mobile"). Every other
  // layer has no such split. An unclassified option (platform=null) falls
  // into web_app, the org's own default recommendation.
  const groupedByPlatform = layer === "frontend"
    ? TECH_STACK_PLATFORMS.map((platform) => ({
        platform,
        options: list.filter((option) =>
          platform === "web_app"
            ? option.platform !== "landing_page" && option.platform !== "institutional_site"
              && option.platform !== "pwa" && option.platform !== "mobile"
            : option.platform === platform
        ),
      })).filter((group) => group.options.length > 0)
    : [];

  return (
    <div className="space-y-1">
      <Select value={value} onChange={(e) => handleSelectChange(e.target.value)}>
        <option value="" disabled>{t("wizard.stack.selectPlaceholder")}</option>
        {currentIsUnlisted && <option value={value}>{value}</option>}
        {layer === "frontend" ? (
          groupedByPlatform.map((group) => (
            <optgroup key={group.platform} label={t(`wizard.stack.platforms.${group.platform}`)}>
              {group.options.map((option) => <option key={option.id} value={option.name}>{option.name}</option>)}
            </optgroup>
          ))
        ) : (
          list.map((option) => <option key={option.id} value={option.name}>{option.name}</option>)
        )}
        <option value={ADD_NEW_VALUE}>{`+ ${t("wizard.stack.addNewOption")}`}</option>
      </Select>
      {selectedDescription && <p className="text-xs text-muted-foreground">{selectedDescription}</p>}
    </div>
  );
}
