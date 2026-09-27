import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowDownToLine, ArrowUpFromLine, Container, HardDrive, Loader2, MemoryStick, Network } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSystemStats } from "@/hooks/useSystemStats";
import { useDockerUsage } from "@/hooks/useSystemControl";
import { useAuthStore } from "@/store/authStore";

/** Reclaimable Docker space that turns the row into a warning. */
const DOCKER_RECLAIMABLE_WARNING_BYTES = 10 * 1000 ** 3;
const DOCKER_POLL_MS = 5 * 60_000;

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

/** Docker's share of the disk under the Disk bar (2026-09-27, Marcelo: "é
 * fundamental esse monitoramento no dashboard") -- on this VPS the disk fills
 * with BuildKit cache, not files, and the bar alone can't say that. Admins
 * only (the endpoint is admin-gated); an error just hides the row, since the
 * disk bar above still tells the main story. */
function DockerDiskRow({ diskPercent }: { diskPercent: number }) {
  const { t } = useTranslation("dashboard");
  const isAdmin = useAuthStore((s) => s.user?.is_admin ?? false);
  const { data } = useDockerUsage({ enabled: isAdmin, refetchInterval: DOCKER_POLL_MS });
  if (!isAdmin || !data) return null;

  const buildCache = data.types.find((type) => type.type === "Build Cache");
  const images = data.types.find((type) => type.type === "Images");
  const reclaimable = (buildCache?.reclaimable ?? 0) + (images?.reclaimable ?? 0);
  const warn = reclaimable >= DOCKER_RECLAIMABLE_WARNING_BYTES || (diskPercent >= 80 && reclaimable > 0);

  return (
    <div className="space-y-1.5 border-l-2 border-muted pl-3">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-sm">
        <span className="flex items-center gap-2 font-medium">
          <Container className="h-4 w-4 text-muted-foreground" />
          {t("systemStats.docker")}
        </span>
        <span className="text-muted-foreground">
          {t("systemStats.dockerBreakdown", {
            cache: formatBytes(buildCache?.size ?? 0),
            images: formatBytes(images?.size ?? 0),
          })}
        </span>
      </div>
      {warn ? (
        <Link
          to="/system-control"
          className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-700 hover:bg-amber-500/20 dark:text-amber-300"
        >
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{t("systemStats.dockerReclaimableWarning", { size: formatBytes(reclaimable) })}</span>
        </Link>
      ) : (
        <p className="text-xs text-muted-foreground">
          {t("systemStats.dockerReclaimable", { size: formatBytes(reclaimable) })}
        </p>
      )}
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
          <DockerDiskRow diskPercent={data.disk.percent_used} />
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
