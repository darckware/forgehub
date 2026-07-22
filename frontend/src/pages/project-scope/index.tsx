import { useEffect, useMemo, useState } from "react";
import { ClipboardList, GitPullRequestArrow, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useProjects } from "@/hooks/useProject";
import { useAddScopeItem, useBlueprintGraph, useProjectScopes, useScopeExecutionStatus, useScopeItems } from "@/hooks/useSystemScope";
import { SystemMapCanvas } from "@/pages/system-map/SystemMapCanvas";

export default function ProjectScopePage() {
  const { t } = useTranslation("projectScope");
  const projects = useProjects(); const [projectId,setProjectId]=useState(""); const scopes=useProjectScopes(projectId);
  const [scopeId,setScopeId]=useState(""); useEffect(()=>setScopeId(scopes.data?.[0]?.id||""),[scopes.data]);
  const scope=scopes.data?.find(x=>x.id===scopeId); const graph=useBlueprintGraph(scope?.blueprint_base_revision_id); const items=useScopeItems(scopeId); const add=useAddScopeItem();
  const executionStatus=useScopeExecutionStatus(scopeId);
  const [form,setForm]=useState({system_element_id:"",change_type:"add",applicability:"required",rationale:"",criterion:""});
  const itemByElement=useMemo(()=>new Map(items.data?.map(x=>[x.system_element_id,x])),[items.data]);
  return <div className="space-y-6"><div className="flex flex-wrap items-start justify-between gap-4"><div><h1 className="text-2xl font-semibold">{t("page.title")}</h1><p className="text-sm text-muted-foreground">{t("page.description")}</p></div>
    {projectId && <Link to={`/projects/${projectId}`}><Button variant="outline" size="sm" className="gap-1.5"><GitPullRequestArrow className="h-4 w-4"/>{t("changeRequest.link")}</Button></Link>}
    </div>
    <Card><CardContent className="grid gap-4 pt-6 md:grid-cols-2"><div><Label>{t("selectors.project")}</Label><Select value={projectId} onChange={e=>setProjectId(e.target.value)}><option value="">{t("selectors.projectPlaceholder")}</option>{projects.data?.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</Select></div><div><Label>{t("selectors.scopeBaseline")}</Label><Select value={scopeId} onChange={e=>setScopeId(e.target.value)} disabled={!projectId}><option value="">{t("selectors.scopePlaceholder")}</option>{scopes.data?.map(s=><option key={s.id} value={s.id}>{t("selectors.revisionOption", { revision: s.revision, status: s.status })}</option>)}</Select></div></CardContent></Card>
    {scope && <Card><CardHeader><CardTitle className="text-base">{t("visualScope.title")}</CardTitle><CardDescription>{t("visualScope.description")}</CardDescription></CardHeader><CardContent>
      <SystemMapCanvas revisionId={scope.blueprint_base_revision_id} graph={graph.data} isLoading={graph.isLoading} readOnly statusByElementId={executionStatus.data}/>
    </CardContent></Card>}
    {scope && <div className="grid gap-6 xl:grid-cols-[360px_1fr]"><Card><CardHeader><CardTitle className="text-base">{t("addItem.title")}</CardTitle><CardDescription>{t("addItem.description")}</CardDescription></CardHeader><CardContent><form className="space-y-3" onSubmit={async e=>{e.preventDefault();await add.mutateAsync({scopeId,...form,acceptance_criteria:form.criterion?[{criterion:form.criterion}]:[]});setForm({...form,system_element_id:"",criterion:""});}}>
      <div><Label>{t("addItem.fields.systemElement")}</Label><Select required value={form.system_element_id} onChange={e=>setForm({...form,system_element_id:e.target.value})}><option value="">{t("addItem.fields.systemElementPlaceholder")}</option>{graph.data?.elements.filter(x=>!itemByElement.has(x.element.id)).map(x=><option key={x.element.id} value={x.element.id}>{x.element.name} · {x.element.element_type}</option>)}</Select></div>
      <div><Label>{t("addItem.fields.change")}</Label><Select value={form.change_type} onChange={e=>setForm({...form,change_type:e.target.value})}>{["add","modify","remove","deprecate","verify"].map(x=><option key={x}>{x}</option>)}</Select></div>
      <div><Label>{t("addItem.fields.applicability")}</Label><Select value={form.applicability} onChange={e=>setForm({...form,applicability:e.target.value})}>{["required","optional","not_applicable"].map(x=><option key={x}>{x}</option>)}</Select></div>
      <div><Label>{t("addItem.fields.rationale")}</Label><Input required={form.applicability==="not_applicable"} value={form.rationale} onChange={e=>setForm({...form,rationale:e.target.value})}/></div>
      <div><Label>{t("addItem.fields.acceptanceCriterion")}</Label><Input placeholder={t("addItem.acceptanceCriterionPlaceholder")} value={form.criterion} onChange={e=>setForm({...form,criterion:e.target.value})}/></div>
      <Button className="w-full" disabled={add.isPending||scope.status!=="draft"}><Plus className="mr-2 h-4 w-4"/>{t("addItem.button")}</Button>
    </form></CardContent></Card>
    <Card><CardHeader><CardTitle className="flex items-center gap-2 text-lg"><ClipboardList className="h-5 w-5"/>{t("coverage.title")}</CardTitle><CardDescription>{t("coverage.summary", { selected: items.data?.length||0, total: graph.data?.elements.length||0 })}</CardDescription></CardHeader><CardContent className="space-y-3">{graph.data?.elements.map(x=>{const item=itemByElement.get(x.element.id);return <div key={x.element.id} className={`rounded-lg border p-4 ${item?"border-primary/30 bg-primary/5":"opacity-60"}`}><div className="flex flex-wrap justify-between gap-2"><div><p className="font-medium">{x.element.name}</p><p className="text-xs text-muted-foreground">{x.element.family} · {x.element.element_type} · {x.element.stable_key}</p></div>{item?<div className="flex gap-2"><Badge>{item.change_type}</Badge><Badge variant="outline">{item.applicability}</Badge></div>:<Badge variant="secondary">{t("coverage.outsideScope")}</Badge>}</div>{item?.acceptance_criteria.map(c=><p key={c.id} className="mt-2 text-sm">✓ {c.criterion}</p>)}</div>})}</CardContent></Card></div>}
  </div>;
}
