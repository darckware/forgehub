import { useTranslation } from "react-i18next";
import type { EnvironmentEntry } from "@/hooks/useMissions";
import { cn } from "@/lib/utils";

/** What is published in each environment and from which commit (§6). No
 * row is "sem registro": a build or container is never read as a release. */
export function MissionEnvironmentsStrip({ environments }: { environments: EnvironmentEntry[] }) {
  const { t, i18n } = useTranslation("missions");
  return (
    <section data-testid="environments-strip" className="space-y-1">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t("env.title")}</h2>
      {environments.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t("env.empty")}</p>
      ) : (
        <div className="flex gap-2 max-md:overflow-x-auto max-md:pb-1 md:flex-wrap">
          {environments.map((env) => (
            <div
              key={`${env.environment}-${env.target}`}
              className={cn("shrink-0 rounded-md border px-2.5 py-1.5 text-xs",
                env.source === "no_record" ? "border-dashed text-muted-foreground" : "bg-card")}
            >
              <span className="font-semibold">{t(`env.${env.environment}`, env.environment)}</span>{" "}
              <span>{env.target}</span>{" "}
              {env.source === "no_record" ? (
                <span>· {t("env.noRecord")}</span>
              ) : (
                <>
                  <code className="font-mono">@ {env.commit_sha?.slice(0, 7)}</code>
                  <span className="text-muted-foreground">
                    {" "}({env.released_at ? new Date(env.released_at).toLocaleString(i18n.language) : ""}
                    {env.released_by ? `, ${env.released_by}` : ""}
                    {", "}{env.task_number ? t("env.task", { number: env.task_number }) : t("env.noTask")}
                    {env.source === "imported" ? `, ${t("env.imported")}` : ""})
                  </span>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
