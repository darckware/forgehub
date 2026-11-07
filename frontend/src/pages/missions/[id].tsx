import { Link, useParams } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { useTranslation } from "react-i18next";
import { Button, buttonVariants } from "@/components/ui/button";
import { MissionExecutionsBoard } from "@/components/missions/MissionExecutionsBoard";
import { useMissionExecutionsViewModel } from "@/hooks/useMissionExecutionsViewModel";

function BoardSkeleton() {
  return (
    <div className="space-y-3" data-testid="board-loading" aria-busy="true">
      <div className="h-8 w-2/3 animate-pulse rounded bg-muted" />
      <div className="h-6 w-full animate-pulse rounded bg-muted" />
      {Array.from({ length: 6 }, (_, i) => <div key={i} className="h-12 w-full animate-pulse rounded bg-muted" />)}
    </div>
  );
}

/** /missions/:projectId — the mission's executions (M0.7). */
export default function MissionDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { t } = useTranslation("missions");
  const vm = useMissionExecutionsViewModel(projectId);
  const admin = useAuthStore((s) => s.user?.is_admin === true);

  if (vm.status === "loading") return <BoardSkeleton />;
  if (vm.status === "error") {
    const message = vm.errorKind === "not_found" ? t("board.notFound")
      : vm.errorKind === "forbidden" ? t("board.forbidden") : t("board.serverError");
    return (
      <div role="alert" data-testid={`board-error-${vm.errorKind}`} className="space-y-3 rounded-lg border p-6 text-sm">
        <p>{message}</p>
        {vm.errorKind === "server" && <Button size="sm" variant="outline" onClick={vm.retry}>{t("board.retry")}</Button>}
      </div>
    );
  }
  return <div className="space-y-4">{admin && <div className="flex justify-end"><Link className={buttonVariants({ variant: "outline" })} to={`/missions/${projectId}/edit`}>{t("form.editTitle")}</Link></div>}<MissionExecutionsBoard vm={vm} /></div>;
}
