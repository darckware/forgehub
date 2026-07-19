import { useTranslation } from "react-i18next";
import { ArrowDownToLine, ArrowUpFromLine, HardDrive, Loader2, MemoryStick, Network } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSystemStats } from "@/hooks/useSystemStats";

function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 GB";
  const gb = bytes / 1024 ** 3;
  return `${gb.toFixed(1)} GB`;
}

function barColor(percent: number): string {
  if (percent >= 90) return "bg-destructive";
  if (percent >= 75) return "bg-amber-500";
  return "bg-emerald-600";
}

function NetworkRow({ interface: iface, rxBytes, txBytes }: { interface: string | null; rxBytes: number; txBytes: number }) {
  const { t } = useTranslation("dashboard");
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-sm">
        <span className="flex items-center gap-2 font-medium">
          <Network className="h-4 w-4 text-muted-foreground" />
          {t("systemStats.network")}{iface ? ` (${iface})` : ""}
        </span>
      </div>
      <div className="flex items-center gap-4 text-sm text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <ArrowDownToLine className="h-3.5 w-3.5" />
          {formatBytes(rxBytes)}
        </span>
        <span className="flex items-center gap-1.5">
          <ArrowUpFromLine className="h-3.5 w-3.5" />
          {formatBytes(txBytes)}
        </span>
      </div>
    </div>
  );
}

function UsageRow({
  icon,
  label,
  usedBytes,
  totalBytes,
  percent,
}: {
  icon: React.ReactNode;
  label: string;
  usedBytes: number;
  totalBytes: number;
  percent: number;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-sm">
        <span className="flex items-center gap-2 font-medium">
          {icon}
          {label}
        </span>
        <span className="text-muted-foreground">
          {formatBytes(usedBytes)} / {formatBytes(totalBytes)} ({percent.toFixed(0)}%)
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full rounded-full transition-all", barColor(percent))}
          style={{ width: `${Math.min(percent, 100)}%` }}
        />
      </div>
    </div>
  );
}

export function SystemStatsCard() {
  const { t } = useTranslation("dashboard");
  const { data, isLoading, isError } = useSystemStats();

  return (
    <div className="space-y-4">
      {isLoading && (
        <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t("systemStats.loading")}
        </div>
      )}
      {isError && (
        <p className="text-xs text-destructive">
          {t("systemStats.hostBridgeError")}
        </p>
      )}
      {data && (
        <>
          <UsageRow
            icon={<MemoryStick className="h-4 w-4 text-muted-foreground" />}
            label={t("systemStats.memory")}
            usedBytes={data.memory.used_bytes}
            totalBytes={data.memory.total_bytes}
            percent={data.memory.percent_used}
          />
          <UsageRow
            icon={<HardDrive className="h-4 w-4 text-muted-foreground" />}
            label={t("systemStats.disk")}
            usedBytes={data.disk.used_bytes}
            totalBytes={data.disk.total_bytes}
            percent={data.disk.percent_used}
          />
          <NetworkRow
            interface={data.network.interface}
            rxBytes={data.network.rx_bytes}
            txBytes={data.network.tx_bytes}
          />
        </>
      )}
    </div>
  );
}
