import { useState } from "react";
import { ToolVersionsCard } from "@/components/ToolVersionsCard";
import { SystemStatsCard } from "@/components/SystemStatsCard";
import { RemoteAccessCard } from "@/components/RemoteAccessCard";
import { ProjectsForgeRouterCard } from "@/components/ProjectsForgeRouterCard";
import { CronsCard } from "@/components/CronsCard";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

type RightColumnTab = "resources" | "remote";

export default function Dashboard() {
  const [tab, setTab] = useState<RightColumnTab>("resources");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">Welcome to ForgeHub.</p>
      </div>
      {/* Left column (Tool Versions) is naturally the tallest card --
          tabbing System Resources/Remote Access into one card on the right
          keeps that column's height close to it, instead of stacking both
          and towering over it whenever the QR code is showing. */}
      <div className="grid items-start gap-6 md:grid-cols-2">
        <ToolVersionsCard />
        <div className="space-y-6">
          <Card>
            <CardHeader className="pb-3">
              <Tabs value={tab} onValueChange={(v) => setTab(v as RightColumnTab)}>
                <TabsList>
                  <TabsTrigger value="resources">System Resources</TabsTrigger>
                  <TabsTrigger value="remote">Remote Access</TabsTrigger>
                </TabsList>
              </Tabs>
            </CardHeader>
            <CardContent>{tab === "resources" ? <SystemStatsCard /> : <RemoteAccessCard />}</CardContent>
          </Card>
          <CronsCard />
        </div>
      </div>
      <ProjectsForgeRouterCard />
    </div>
  );
}
