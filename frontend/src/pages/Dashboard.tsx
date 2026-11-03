import { useAuthStore } from "@/store/authStore";
import { ServerMonitoringDashboard } from "@/components/ServerMonitoringDashboard";
import { useTranslation } from "react-i18next";
import { ToolVersionsCard } from "@/components/ToolVersionsCard";
import { SystemStatsCard } from "@/components/SystemStatsCard";
import { CronsCard } from "@/components/CronsCard";
import { Card, CardContent } from "@/components/ui/card";

export default function Dashboard() {
  const { t } = useTranslation("dashboard");
  const isAdmin = useAuthStore(s => s.user?.is_admin === true);

  return (
    <div className="space-y-4 md:space-y-6">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground">{t("welcome")}</p>
      </div>
      {/* Independent card heights avoid empty grid cells. Keep a single
          reading order and let cards fit the viewport without fixed heights. */}
      <div className="columns-1 gap-4 md:columns-2 md:gap-6">
        <div className="mb-4 min-w-0 break-inside-avoid md:mb-6">
          <Card>
            <CardContent className="pt-6"><SystemStatsCard /></CardContent>
          </Card>
        </div>
        {isAdmin && <ServerMonitoringDashboard />}
        <div className="mb-4 min-w-0 break-inside-avoid md:mb-6">
          <CronsCard />
        </div>
        <div className="mb-4 min-w-0 break-inside-avoid md:mb-6">
          <ToolVersionsCard />
        </div>
      </div>
    </div>
  );
}
