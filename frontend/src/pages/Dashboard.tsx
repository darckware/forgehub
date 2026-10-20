import { useTranslation } from "react-i18next";
import { ToolVersionsCard } from "@/components/ToolVersionsCard";
import { SystemStatsCard } from "@/components/SystemStatsCard";
import { CliForgeRouterCard } from "@/components/CliForgeRouterCard";
import { CronsCard } from "@/components/CronsCard";
import { Card, CardContent } from "@/components/ui/card";

export default function Dashboard() {
  const { t } = useTranslation("dashboard");

  return (
    <div className="space-y-4 md:space-y-6">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground">{t("welcome")}</p>
      </div>
      {/* Left column (Tool Versions) is naturally the tallest card. Keeping
          System Resources in the right column keeps the two columns aligned
          without adding a second dashboard control surface.
          grid-cols-1 (not the implicit track) + min-w-0 on each column: an
          implicit grid column sizes to its content's max-content width, so
          on a phone the cards grew past the viewport and got clipped. */}
      <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-2 md:gap-6">
        <div className="min-w-0">
          <ToolVersionsCard />
        </div>
        <div className="min-w-0 space-y-4 md:space-y-6">
          <Card>
            <CardContent className="pt-6"><SystemStatsCard /></CardContent>
          </Card>
          <CronsCard />
        </div>
      </div>
      <CliForgeRouterCard />
    </div>
  );
}
