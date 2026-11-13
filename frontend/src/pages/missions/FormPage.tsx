import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/PageHeader";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useAuthStore } from "@/store/authStore";
import { useProducts, useAllProductVersions } from "@/hooks/useProduct";
import { useAgents } from "@/hooks/useAgent";
import { useMissionRecord, useSaveMission, useCancelMission, missionError } from "@/hooks/useMissionManagement";
import { MissionTeamEditor } from "@/components/missions/MissionTeamEditor";
import { WorkingDirPicker } from "@/components/WorkingDirPicker";

const PRODUCT_KINDS = ["software", "service", "infrastructure", "client_it"] as const;

export default function MissionFormPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const admin = useAuthStore((s) => s.user?.is_admin === true);
  const { t } = useTranslation("missions");
  return admin ? <MissionEditor key={projectId ?? "new"} projectId={projectId} /> : <div role="alert" className="rounded-lg border p-6">{t("form.adminOnly")}</div>;
}
function MissionEditor({ projectId }: { projectId?: string }) {
  const { t } = useTranslation("missions"); const navigate = useNavigate();
  const products = useProducts(); const versions = useAllProductVersions(); const agents = useAgents();
  const query = useMissionRecord(projectId); const save = useSaveMission(projectId); const cancel = useCancelMission(projectId);
  const [name, setName] = useState(""); const [description, setDescription] = useState("");
  const [version, setVersion] = useState(""); const [orchestrator, setOrchestrator] = useState("");
  const [directory, setDirectory] = useState(""); const [priority, setPriority] = useState("100");
  const [deadline, setDeadline] = useState(""); const [reason, setReason] = useState("");
  const [newProduct, setNewProduct] = useState(false); const [newProductName, setNewProductName] = useState(""); const [newProductKind, setNewProductKind] = useState<string>("software");
  const [error, setError] = useState(""); const [confirmation, setConfirmation] = useState<"cancel" | "leave" | null>(null);
  const [dirty, setDirty] = useState(false); const initialized = useRef<string | null>(null); const submitting = useRef(false);
  const [teamDirty, setTeamDirty] = useState(false);
  const loadedRowVersion = useRef<number | null>(null);
  useEffect(() => {
    const m = query.data; if (!m || initialized.current === projectId) return;
    initialized.current = projectId ?? null; loadedRowVersion.current = m.row_version; setName(m.name); setDescription(m.description ?? "");
    setDirectory(m.working_directory_path ?? ""); setVersion(m.product_version_id); setOrchestrator(m.orchestrator_agent_id);
    setPriority(String(m.priority));
    if (m.deadline_at) { const d = new Date(m.deadline_at); setDeadline(new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16)); }
  }, [query.data, projectId]);
  useEffect(() => {
    if (projectId || orchestrator) return;
    const athos = agents.data?.find((a) => a.profile_slug === "athos" && a.is_active && a.status === "active");
    if (athos) setOrchestrator(athos.id);
  }, [agents.data, orchestrator, projectId]);
  useEffect(() => { const guard = (e: BeforeUnloadEvent) => { if (dirty || teamDirty) { e.preventDefault(); e.returnValue = ""; } }; window.addEventListener("beforeunload", guard); return () => window.removeEventListener("beforeunload", guard); }, [dirty, teamDirty]);
  const m = query.data; const terminal = m?.state === "completed" || m?.state === "cancelled";
  const fixed = Boolean(m && (m.current_baseline_id || !(m.state === "draft" || (m.state === "planning" && m.planning_stage === "draft_plan"))));
  const loading = products.isLoading || versions.isLoading || agents.isLoading || (Boolean(projectId) && query.isLoading);
  const loadError = products.isError || versions.isError || agents.isError || query.isError;
  const leave = () => { if (dirty || teamDirty) setConfirmation("leave"); else navigate(projectId ? `/missions/${projectId}` : "/missions"); };
  async function submit(e: FormEvent) {
    e.preventDefault(); if (submitting.current || terminal) return;
    if (teamDirty) { setError(t("team.unsaved")); return; }
    const invalid = Array.from((e.currentTarget as HTMLFormElement).elements).find((field) =>
      (field instanceof HTMLInputElement || field instanceof HTMLSelectElement || field instanceof HTMLTextAreaElement) && !field.validity.valid);
    if (invalid instanceof HTMLElement) { setError(t("form.invalid")); invalid.focus(); return; }
    const isNewProduct = !projectId && newProduct;
    if (!name.trim() || (!projectId && ((!version && !isNewProduct) || !orchestrator))) { setError(t("form.required")); return; }
    if (isNewProduct && (!newProductName.trim() || !directory.trim())) { setError(t("form.newProductRequired")); return; }
    submitting.current = true; setError("");
    const common = { priority: Number(priority), deadline_at: deadline ? new Date(deadline).toISOString() : null };
    const metadata = { name: name.trim(), description: description.trim() || null, working_directory_path: directory.trim() || null };
    try {
      const result = await save.mutateAsync(projectId ? { ...common, ...(!fixed ? metadata : {}), expected_row_version: loadedRowVersion.current, reason: reason.trim() || undefined }
        : { ...metadata, ...common, ...(isNewProduct ? { new_product: { name: newProductName.trim(), kind: newProductKind } } : { product_version_id: version }), orchestrator_agent_id: orchestrator, project_type: "mission", autonomy_level: "N0" });
      setDirty(false); navigate(`/missions/${result.project_id}`);
    } catch (err) { setError(missionError(err, t("form.saveError"))); }
    finally { submitting.current = false; }
  }
  async function confirmCancel() {
    if (!m || submitting.current) return; submitting.current = true; setError("");
    try { await cancel.mutateAsync({ expected_row_version: loadedRowVersion.current!, reason: reason.trim() }); setDirty(false); navigate("/missions"); }
    catch (err) { setError(missionError(err, t("form.saveError"))); }
    finally { submitting.current = false; }
  }
  if (loading) return <p role="status">{t("form.loading")}</p>;
  if (loadError) return <div className="mx-auto max-w-4xl space-y-6">
    <PageHeader title={t(projectId ? "form.editTitle" : "form.createTitle")} description={t("form.description")} />
    <div role="alert" className="space-y-3 rounded-lg border p-4 text-sm">
      <p>{t("form.loadError")}</p>
      <ul className="list-inside list-disc space-y-1 text-muted-foreground">
        {products.isError && <li>{t("form.productsLoadError")}</li>}
        {versions.isError && <li>{t("form.versionsLoadError")}</li>}
        {agents.isError && <li>{t("form.agentsLoadError")}</li>}
        {query.isError && <li>{t("form.recordLoadError")}</li>}
      </ul>
      <div className="flex flex-wrap gap-3">
        <Button onClick={() => { initialized.current = null; if (products.isError) void products.refetch(); if (versions.isError) void versions.refetch(); if (agents.isError) void agents.refetch(); if (projectId && query.isError) void query.refetch(); }}>{t("board.retry")}</Button>
        <Link className={buttonVariants({ variant: "outline" })} to="/missions">{t("board.back")}</Link>
      </div>
    </div>
  </div>;
  return <div className="mx-auto max-w-4xl space-y-6">
    <PageHeader title={t(projectId ? "form.editTitle" : "form.createTitle")} description={t("form.description")} actions={<Button variant="outline" onClick={leave}>{t("form.back")}</Button>} />
    {terminal && <p role="status" className="rounded-lg border p-4">{t("form.terminal")}</p>}
    {error && <p role="alert" className="rounded-lg border border-destructive p-3 text-sm">{error}</p>}
    {fixed && !terminal && <p className="text-sm text-muted-foreground">{t("form.fixed")}</p>}
    <form noValidate className="space-y-5 rounded-xl border bg-card p-4 sm:p-6" onSubmit={submit} onChange={() => setDirty(true)}>
      <fieldset disabled={terminal || save.isPending || cancel.isPending} className="space-y-5">
        <label className="block space-y-2"><span>{t("form.name")}</span><Input required maxLength={255} value={name} disabled={fixed} onChange={(e) => setName(e.target.value)} /></label>
        <label className="block space-y-2"><span>{t("form.context")}</span><Textarea className="resize-none" value={description} disabled={fixed} onChange={(e) => setDescription(e.target.value)} rows={5} /></label>
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <div className="space-y-2">
            <label className="block space-y-2"><span>{t("form.version")}</span>{newProduct ? <p className="flex h-10 items-center rounded-md border border-dashed px-3 text-sm text-muted-foreground">{t("form.newProductSelected")}</p> : <select required={!newProduct} disabled={Boolean(projectId)} className="h-10 w-full rounded-md border bg-background px-3 text-sm" value={version} onChange={(e) => setVersion(e.target.value)}><option value="">{t("form.select")}</option>{versions.data?.filter((v) => v.id === version || !["published", "deprecated"].includes(v.status)).map((v) => <option key={v.id} value={v.id}>{products.data?.find((p) => p.id === v.product_id)?.name ?? v.product_id} · {v.version}</option>)}</select>}</label>
            {!projectId && <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4" checked={newProduct} onChange={(e) => { setNewProduct(e.target.checked); if (e.target.checked) setVersion(""); }} />{t("form.newProductCheckbox")}</label>}
          </div>
          <label className="block space-y-2"><span>{t("form.orchestrator")}</span><select required disabled={Boolean(projectId)} className="h-10 w-full rounded-md border bg-background px-3 text-sm" value={orchestrator} onChange={(e) => setOrchestrator(e.target.value)}><option value="">{t("form.select")}</option>{agents.data?.filter((a) => a.id === orchestrator || (a.is_active && a.status === "active")).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
          {newProduct && !projectId && <div className="space-y-4 rounded-lg border border-dashed p-4 sm:col-span-2">
            <p className="text-sm text-muted-foreground">{t("form.newProductHint")}</p>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <label className="block space-y-2"><span>{t("form.newProductName")}</span><Input required maxLength={255} value={newProductName} onChange={(e) => setNewProductName(e.target.value)} /></label>
              <label className="block space-y-2"><span>{t("form.newProductKind")}</span><select className="h-10 w-full rounded-md border bg-background px-3 text-sm" value={newProductKind} onChange={(e) => setNewProductKind(e.target.value)}>{PRODUCT_KINDS.map((k) => <option key={k} value={k}>{t(`form.productKind.${k}`)}</option>)}</select></label>
            </div>
          </div>}
          <label className="block space-y-2"><span>{t("form.priority")}</span><Input required type="number" min={1} max={1000} value={priority} onChange={(e) => setPriority(e.target.value)} /></label>
          <label className="block space-y-2"><span>{t("form.deadline")}</span><Input type="datetime-local" value={deadline} onChange={(e) => setDeadline(e.target.value)} /></label>
          <label className="block space-y-2 sm:col-span-2"><span>{t("form.directory")}{newProduct && !projectId ? " *" : ""}</span>
            <div className="flex items-center gap-2">
              <Input disabled={fixed} required={newProduct && !projectId} maxLength={1024} placeholder="/root/project/..." value={directory} onChange={(e) => setDirectory(e.target.value)} />
              {!fixed && !terminal && <WorkingDirPicker workingDir={directory || undefined} onSelect={(path) => { setDirectory(path ?? ""); setDirty(true); }} />}
            </div>
            {newProduct && !projectId && <span className="block text-xs text-muted-foreground">{t("form.directoryDocsHint")}</span>}
          </label>
        </div>
        {projectId && <label className="block space-y-2"><span>{t("form.reason")}</span><Textarea className="resize-none" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={4000} /></label>}
        <p className="text-sm text-muted-foreground">{t("form.draftHint")}</p>
        {!terminal && <div className="flex flex-wrap gap-2"><Button type="submit" disabled={save.isPending}>{t(save.isPending ? "form.saving" : projectId ? "form.save" : "form.create")}</Button><Button type="button" variant="outline" onClick={leave}>{t("form.back")}</Button>{projectId && <Button type="button" variant="destructive" disabled={!reason.trim()} onClick={() => setConfirmation("cancel")}>{t("form.cancelMission")}</Button>}</div>}
      </fieldset>
    </form>
    <section className="space-y-2 rounded-xl border p-4 sm:p-6"><h2 className="text-lg font-semibold">{t("team.contextTitle")}</h2><p className="text-sm text-muted-foreground">{t("team.contextDescription")}</p></section>
    {projectId && m && <MissionTeamEditor projectId={projectId} orchestratorId={m.orchestrator_agent_id} readOnly={terminal} onDirtyChange={setTeamDirty} />}
    <ConfirmDialog open={confirmation !== null} title={t(confirmation === "cancel" ? "form.cancelTitle" : "form.discardTitle")} description={t(confirmation === "cancel" ? "form.cancelDescription" : "form.discardDescription", { name })} confirmLabel={t(confirmation === "cancel" ? "form.cancelMission" : "form.discard")} loading={cancel.isPending} dismissDisabled={cancel.isPending} error={error || null} onCancel={() => setConfirmation(null)} onConfirm={() => { if (confirmation === "cancel") void confirmCancel(); else { setDirty(false); navigate(projectId ? `/missions/${projectId}` : "/missions"); } }} />
  </div>;
}
