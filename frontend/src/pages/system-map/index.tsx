import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { GitBranch, Loader2, Plus, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useProducts } from "@/hooks/useProduct";
import { useAddSystemElement, useAddSystemRelation, useBlueprint, useBlueprintGraph, useValidateBlueprint } from "@/hooks/useSystemScope";

const familyTypes: Record<string, string[]> = {
  business:["capability","module","persona"], process:["journey","process","process_step","use_case"],
  experience:["application","channel","route","screen","form","report","ui_component"], interface:["api","endpoint","command","query","event","webhook","integration"],
  domain:["domain_entity","value_object","business_rule","authorization_rule"], application:["service","handler","class","method","workflow","job"],
  data:["datastore","schema","table","field","index","view","procedure","migration"], runtime:["runtime_component","queue","cache","deployment_unit","environment_target"],
  assurance:["test_scenario","metric","log_signal","alert","slo","health_check"],
};
export default function SystemMapPage() {
  const [params, setParams] = useSearchParams(); const products = useProducts();
  const productId = params.get("product") || ""; const blueprint = useBlueprint(productId); const revisionId = blueprint.data?.current_revision?.id;
  const graph = useBlueprintGraph(revisionId); const addElement = useAddSystemElement(); const addRelation = useAddSystemRelation(); const validate = useValidateBlueprint();
  const [element, setElement] = useState({ stable_key:"", family:"experience", element_type:"screen", name:"" });
  const [relation, setRelation] = useState({ from_element_id:"", to_element_id:"", relation_type:"depends_on" });
  useEffect(() => { setElement(value => ({...value, element_type:familyTypes[value.family][0]})); }, [element.family]);
  const grouped = useMemo(() => Object.entries((graph.data?.elements || []).reduce<Record<string, NonNullable<typeof graph.data>["elements"]>>((all, item) => {
    (all[item.element.family] ||= []).push(item); return all;
  }, {})), [graph.data]);
  return <div className="space-y-6">
    <div><h1 className="text-2xl font-semibold">System Map</h1><p className="text-sm text-muted-foreground">Trace the system from business intent through screens, rules, code, data, deployment and evidence.</p></div>
    <Card><CardContent className="pt-6"><Label>Product</Label><Select value={productId} onChange={e => setParams(e.target.value ? {product:e.target.value} : {})}><option value="">Select a product</option>{products.data?.map(p => <option key={p.id} value={p.id}>{p.name} · {p.status}</option>)}</Select></CardContent></Card>
    {productId && blueprint.data && <>
      <div className="grid gap-4 md:grid-cols-3"><Card><CardHeader><CardDescription>Map</CardDescription><CardTitle className="text-lg">{blueprint.data.blueprint.name}</CardTitle></CardHeader></Card><Card><CardHeader><CardDescription>Revision</CardDescription><CardTitle className="text-lg">#{blueprint.data.current_revision?.revision} <Badge variant="outline">{blueprint.data.current_revision?.status}</Badge></CardTitle></CardHeader></Card><Card><CardHeader><CardDescription>Coverage</CardDescription><CardTitle className="text-lg">{graph.data?.elements.length || 0} elements · {graph.data?.relations.length || 0} links</CardTitle></CardHeader></Card></div>
      <div className="grid gap-6 xl:grid-cols-[360px_1fr]">
        <div className="space-y-6"><Card><CardHeader><CardTitle className="text-base">Add system element</CardTitle></CardHeader><CardContent><form className="space-y-3" onSubmit={async e => {e.preventDefault(); if(!revisionId) return; await addElement.mutateAsync({revisionId,...element}); setElement({...element,stable_key:"",name:""});}}>
          <div><Label>Stable key</Label><Input required pattern="[a-z0-9][a-z0-9._-]*" placeholder="screen.login" value={element.stable_key} onChange={e=>setElement({...element,stable_key:e.target.value})}/></div>
          <div><Label>Name</Label><Input required value={element.name} onChange={e=>setElement({...element,name:e.target.value})}/></div>
          <div><Label>Layer</Label><Select value={element.family} onChange={e=>setElement({...element,family:e.target.value})}>{Object.keys(familyTypes).map(f=><option key={f}>{f}</option>)}</Select></div>
          <div><Label>Type</Label><Select value={element.element_type} onChange={e=>setElement({...element,element_type:e.target.value})}>{familyTypes[element.family].map(t=><option key={t}>{t}</option>)}</Select></div>
          <Button className="w-full" disabled={addElement.isPending || blueprint.data.current_revision?.status!=="draft"}><Plus className="mr-2 h-4 w-4"/>Add</Button>
        </form></CardContent></Card>
        <Card><CardHeader><CardTitle className="text-base">Connect elements</CardTitle></CardHeader><CardContent><form className="space-y-3" onSubmit={async e=>{e.preventDefault();if(revisionId) await addRelation.mutateAsync({revisionId,...relation});}}>
          <Select required value={relation.from_element_id} onChange={e=>setRelation({...relation,from_element_id:e.target.value})}><option value="">From</option>{graph.data?.elements.map(x=><option key={x.element.id} value={x.element.id}>{x.element.name}</option>)}</Select>
          <Select value={relation.relation_type} onChange={e=>setRelation({...relation,relation_type:e.target.value})}>{["contains","precedes","navigates_to","invokes","implements","governed_by","reads","writes","depends_on","persists_as","runs_on","deployed_to","verified_by"].map(t=><option key={t}>{t}</option>)}</Select>
          <Select required value={relation.to_element_id} onChange={e=>setRelation({...relation,to_element_id:e.target.value})}><option value="">To</option>{graph.data?.elements.map(x=><option key={x.element.id} value={x.element.id}>{x.element.name}</option>)}</Select>
          <Button variant="outline" className="w-full" disabled={addRelation.isPending}>Connect</Button>
        </form></CardContent></Card></div>
        <Card><CardHeader><div className="flex items-center justify-between gap-3"><div><CardTitle className="flex items-center gap-2 text-lg"><GitBranch className="h-5 w-5"/>Scope graph</CardTitle><CardDescription>Elements grouped by engineering layer.</CardDescription></div><Button variant="outline" onClick={()=>revisionId&&validate.mutate(revisionId)} disabled={validate.isPending}>{validate.isPending?<Loader2 className="mr-2 h-4 w-4 animate-spin"/>:<ShieldCheck className="mr-2 h-4 w-4"/>}Validate</Button></div></CardHeader><CardContent className="space-y-5">
          {validate.data && <div className={`rounded-md border p-3 text-sm ${validate.data.valid?"border-emerald-500/40 bg-emerald-500/5":"border-destructive/40 bg-destructive/5"}`}><p className="font-medium">{validate.data.valid?"Map is structurally valid":"Map has blocking issues"}</p>{validate.data.issues.map((x,i)=><p key={i} className="mt-1 text-xs text-muted-foreground">{x.severity}: {x.message}</p>)}</div>}
          {grouped.map(([family,items])=><section key={family}><h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{family}</h3><div className="grid gap-2 md:grid-cols-2">{items?.map(x=><div key={x.element.id} className="rounded-md border p-3"><div className="flex justify-between gap-2"><span className="font-medium">{x.element.name}</span><Badge variant="secondary">{x.element.element_type}</Badge></div><code className="text-xs text-muted-foreground">{x.element.stable_key}</code></div>)}</div></section>)}
          {!graph.isLoading && !graph.data?.elements.length && <p className="text-sm text-muted-foreground">Add the first element to begin the system timeline.</p>}
        </CardContent></Card>
      </div>
    </>}
  </div>;
}
