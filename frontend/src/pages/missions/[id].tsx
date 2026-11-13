import { Link, useParams } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { useAuthStore } from "@/store/authStore";
import { useTranslation } from "react-i18next";
import { Button, buttonVariants } from "@/components/ui/button";
import { MissionAcceptance } from "@/components/missions/MissionAcceptance";
import { MissionCriteria } from "@/components/missions/MissionCriteria";
import { MissionDocsCard } from "@/components/missions/MissionDocsCard";
import { MissionExecutionsBoard } from "@/components/missions/MissionExecutionsBoard";
import { MissionPhases } from "@/components/missions/MissionPhases";
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
  const board = vm.board;
  const canManageCriteria = admin && board != null
    && ["draft", "planning"].includes(board.mission.state) && board.mission.baseline === null;
  const reviewers = board?.tasks.flatMap(task => task.reviewer_candidates) ?? [];
  return <div className="space-y-4">
    {admin && <div className="flex justify-end"><Link className={buttonVariants({ variant: "outline" })} to={`/missions/${projectId}/edit`}>{t("form.editTitle")}</Link></div>}
    {board?.mission.product_registration_pending && <div role="status" data-testid="product-registration-pending"
      className="flex gap-3 rounded-lg border border-amber-500/50 bg-amber-500/10 p-4 text-sm">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
      <div className="space-y-1">
        <p className="font-medium">{t("detail.productPendingTitle")}</p>
        <p className="text-muted-foreground">{t("detail.productPendingBody")}</p>
      </div>
    </div>}
    {admin && board && <MissionDocsCard workingDirectory={board.mission.working_directory_path} />}
    {projectId && board && <MissionCriteria projectId={projectId} tasks={board.tasks} reviewers={reviewers}
      canManage={canManageCriteria} />}
    {board?.mission.state === "awaiting_acceptance" && projectId && <MissionAcceptance projectId={projectId} canAct={admin} />}
    {projectId && board && <MissionPhases projectId={projectId} phases={board.phases}
      canEdit={canManageCriteria} canDecide={admin} />}
    <MissionExecutionsBoard vm={vm} />
  </div>;
}
