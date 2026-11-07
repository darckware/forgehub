import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAgents } from "@/hooks/useAgent";
import { PROJECT_AGENT_ROLES, useProjectMemberships } from "@/hooks/useOrchestration";
import { missionError, useApplyMissionMember } from "@/hooks/useMissionManagement";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

/** Uses mission membership rules rather than generic automation permissions. */
export function MissionTeamEditor({ projectId, orchestratorId, readOnly, onDirtyChange }: {
  projectId: string; orchestratorId: string; readOnly: boolean; onDirtyChange: (dirty: boolean) => void;
}) {
  const { t } = useTranslation("missions");
  const { t: automation } = useTranslation("automation");
  const agents = useAgents();
  const members = useProjectMemberships(projectId);
  const apply = useApplyMissionMember(projectId);
  const [agentId, setAgentId] = useState("");
  const [role, setRole] = useState("planner");
  const [responsibilities, setResponsibilities] = useState("");
  const [canReview, setCanReview] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [command, setCommand] = useState<Parameters<typeof apply.mutateAsync>[0] | null>(null);
  const submitting = useRef(false);
  const existing = members.data?.find((m) => m.agent_id === agentId);
  const coordinator = agentId === orchestratorId;
  function selectAgent(id: string) {
    const member = members.data?.find((m) => m.agent_id === id);
    setAgentId(id); setRole(id === orchestratorId ? "coordinator" : member?.role ?? "planner");
    setResponsibilities(member?.responsibilities ?? ""); setCanReview(member?.can_review ?? false);
    setSuccess(false); setError("");
  }
  async function confirm() {
    if (!command || submitting.current) return;
    submitting.current = true; setError("");
    try { await apply.mutateAsync(command); setCommand(null); setSuccess(true); onDirtyChange(false); }
    catch (err) { setError(missionError(err, t("form.saveError"))); }
    finally { submitting.current = false; }
  }
  const name = (id?: string | null) => agents.data?.find((a) => a.id === id)?.name ?? id;
  return <section className="space-y-4 rounded-xl border bg-card p-4 sm:p-6" aria-labelledby="mission-team-title">
    <h2 id="mission-team-title" className="text-lg font-semibold">{t("team.title")}</h2>
    <p className="text-sm text-muted-foreground">{t("team.description")}</p>
    {(agents.isLoading || members.isLoading) ? <p role="status">{t("form.loading")}</p>
      : (agents.isError || members.isError) ? <div role="alert"><p>{t("form.loadError")}</p><Button variant="outline" onClick={() => { void agents.refetch(); void members.refetch(); }}>{t("board.retry")}</Button></div>
      : <>
        <ul className="space-y-2 text-sm">{members.data?.map((member) => <li key={member.id} className="break-words rounded-md border p-3">
          <span className="font-medium">{name(member.agent_id)}</span> · {automation(`roles.${member.role}`)} · {t(`team.status.${member.status}`)}
          {member.can_review && <span> · {t("team.reviewer")}</span>}
          {member.responsibilities && <p className="mt-1 whitespace-pre-wrap text-muted-foreground">{member.responsibilities}</p>}
        </li>)}</ul>
        {!members.data?.length && <p>{t("team.empty")}</p>}
        {!readOnly && <form className="space-y-4" noValidate onChange={() => onDirtyChange(true)} onSubmit={(e) => {
          e.preventDefault(); setSuccess(false); setError("");
          if (!agentId || !responsibilities.trim()) { setError(t("team.required")); return; }
          setCommand({ idempotency_key: crypto.randomUUID(), operations: [{
            op: existing?.status === "active" ? "update" : "add", agent_id: agentId,
            role: coordinator ? "coordinator" : role, responsibilities: responsibilities.trim(), can_review: canReview,
          }] });
        }}>
          <fieldset disabled={apply.isPending} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block space-y-2"><span>{t("team.agent")}</span><Select value={agentId} onChange={(e) => selectAgent(e.target.value)}><option value="">{t("form.select")}</option>{agents.data?.filter((a) => (a.is_active && a.status === "active") || members.data?.some((member) => member.agent_id === a.id)).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</Select></label>
              <label className="block space-y-2"><span>{t("team.role")}</span><Select value={role} disabled={coordinator} onChange={(e) => setRole(e.target.value)}>{PROJECT_AGENT_ROLES.filter((r) => r !== "coordinator" || coordinator).map((r) => <option key={r} value={r}>{automation(`roles.${r}`)}</option>)}</Select></label>
            </div>
            <label className="block space-y-2"><span>{t("team.responsibilities")}</span><Textarea className="resize-none" rows={4} maxLength={2000} value={responsibilities} onChange={(e) => setResponsibilities(e.target.value)} /></label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={canReview} onChange={(e) => setCanReview(e.target.checked)} />{t("team.canReview")}</label>
            <p className="text-sm text-muted-foreground">{t("team.approvalHint")}</p>
            <div className="flex flex-wrap gap-2"><Button type="submit">{t("team.save")}</Button><Button type="button" variant="outline" onClick={() => { selectAgent(""); onDirtyChange(false); }}>{t("team.reset")}</Button>{existing && !coordinator && existing.status === "active" && <Button type="button" variant="outline" onClick={() => { setError(""); setCommand({ idempotency_key: crypto.randomUUID(), operations: [{ op: "release", agent_id: agentId }] }); }}>{t("team.release")}</Button>}</div>
          </fieldset>
        </form>}
        {error && !command && <p role="alert">{error}</p>}
        {success && <p role="status">{t("team.saved")}</p>}
      </>}
    <ConfirmDialog open={command !== null} title={t(command?.operations[0].op === "release" ? "team.release" : "team.confirm")} description={t("team.confirmDescription", { name: name(agentId) })} confirmLabel={t(command?.operations[0].op === "release" ? "team.release" : "team.confirm")} loading={apply.isPending} dismissDisabled={apply.isPending} error={error || null} onCancel={() => setCommand(null)} onConfirm={() => { void confirm(); }} />
  </section>;
}
