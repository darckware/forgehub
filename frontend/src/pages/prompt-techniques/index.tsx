import { useMemo, useState } from "react";
import { ChevronDown, ChevronUp, Search, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { PROMPT_TECHNIQUE_CATEGORIES, usePromptTechniques } from "@/hooks/usePromptTechniques";

export default function PromptTechniquesPage() {
  const { t } = useTranslation("promptTechniques");
  const { data: techniques = [], isLoading, isError } = usePromptTechniques();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [expanded, setExpanded] = useState<string | null>(null);

  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return techniques.filter((item) => {
      if (category !== "all" && item.category !== category) return false;
      if (!needle) return true;
      return [item.name, item.summary, item.when_to_use, item.when_to_avoid, item.code]
        .filter(Boolean)
        .some((value) => value!.toLocaleLowerCase().includes(needle));
    });
  }, [category, query, techniques]);

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <header>
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-primary/10 p-2"><Sparkles className="h-5 w-5 text-primary" /></div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">{t("title")}</h1>
            <p className="text-sm text-muted-foreground">{t("description")}</p>
          </div>
        </div>
      </header>

      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("search")} className="pl-9" />
        </div>
        <select
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          className="h-10 rounded-md border border-input bg-background px-3 text-sm sm:w-60"
        >
          <option value="all">{t("allCategories")}</option>
          {PROMPT_TECHNIQUE_CATEGORIES.map((value) => (
            <option key={value} value={value}>{t(`categories.${value}`)}</option>
          ))}
        </select>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">{t("loading")}</p>}
      {isError && <p className="text-sm text-destructive">{t("error")}</p>}
      {!isLoading && !isError && (
        <>
          <p className="text-xs text-muted-foreground">{t("resultCount", { count: visible.length })}</p>
          <div className="grid gap-3 md:grid-cols-2">
            {visible.map((item) => {
              const open = expanded === item.code;
              return (
                <button
                  key={item.code}
                  type="button"
                  onClick={() => setExpanded(open ? null : item.code)}
                  className={cn(
                    "rounded-xl border bg-card p-4 text-left shadow-sm transition hover:border-primary/40",
                    open && "border-primary/50 ring-1 ring-primary/20"
                  )}
                >
                  <div className="flex items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="font-semibold">{item.name}</h2>
                        <Badge variant="secondary">{t(`categories.${item.category}`)}</Badge>
                        <Badge variant="outline">{t(`effort.${item.effort}`)}</Badge>
                      </div>
                      <p className="mt-2 text-sm text-muted-foreground">{item.summary}</p>
                    </div>
                    {open ? <ChevronUp className="h-4 w-4 shrink-0" /> : <ChevronDown className="h-4 w-4 shrink-0" />}
                  </div>
                  {open && (
                    <div className="mt-4 space-y-3 border-t pt-3 text-sm">
                      <div><p className="font-medium">{t("whenToUse")}</p><p className="text-muted-foreground">{item.when_to_use}</p></div>
                      {item.when_to_avoid && <div><p className="font-medium">{t("whenToAvoid")}</p><p className="text-muted-foreground">{item.when_to_avoid}</p></div>}
                      <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                        <span>{t("selectionMode")}: {t(`selection.${item.selection_mode}`)}</span>
                        <span>•</span>
                        <span>{t("version", { version: item.template_version })}</span>
                        <span>•</span>
                        <code>{item.code}</code>
                      </div>
                    </div>
                  )}
                </button>
              );
            })}
          </div>
          {visible.length === 0 && <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">{t("empty")}</p>}
        </>
      )}
    </div>
  );
}
