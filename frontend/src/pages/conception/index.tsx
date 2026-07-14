import { useState } from "react";
import { Link } from "react-router-dom";
import { Lightbulb, Loader2, Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useAuthorizeDeliveryPlanning, useConcept, useCreateIdea, useDevelopmentRequests, useSubmitConcept } from "@/hooks/useSystemScope";

export default function ConceptionPage() {
  const requests = useDevelopmentRequests();
  const create = useCreateIdea();
  const [selectedProduct, setSelectedProduct] = useState("");
  const concept = useConcept(selectedProduct);
  const submitConcept = useSubmitConcept();
  const authorize = useAuthorizeDeliveryPlanning();
  const [delivery, setDelivery] = useState({ version: "0.1.0", project_name: "", owner: "" });
  const [form, setForm] = useState({ name: "", problem_statement: "", vision: "", scope_summary: "", requested_by: "" });
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    await create.mutateAsync(form);
    setForm({ name: "", problem_statement: "", vision: "", scope_summary: "", requested_by: "" });
  };
  return <div className="space-y-6">
    <div><h1 className="text-2xl font-semibold">Conception</h1><p className="text-sm text-muted-foreground">Transform an idea into a versioned, reviewable product definition before execution begins.</p></div>
    <div className="grid gap-6 xl:grid-cols-[minmax(320px,420px)_1fr]">
      <Card><CardHeader><CardTitle className="flex items-center gap-2 text-lg"><Lightbulb className="h-5 w-5"/>Capture idea</CardTitle><CardDescription>This creates a concept product and its first System Map revision.</CardDescription></CardHeader>
        <CardContent><form className="space-y-4" onSubmit={submit}>
          <div><Label>Name</Label><Input required value={form.name} onChange={e => setForm({...form, name:e.target.value})}/></div>
          <div><Label>Problem statement</Label><Textarea required rows={4} value={form.problem_statement} onChange={e => setForm({...form, problem_statement:e.target.value})}/></div>
          <div><Label>Vision</Label><Textarea rows={3} value={form.vision} onChange={e => setForm({...form, vision:e.target.value})}/></div>
          <div><Label>Initial scope</Label><Textarea rows={3} value={form.scope_summary} onChange={e => setForm({...form, scope_summary:e.target.value})}/></div>
          <div><Label>Requested by</Label><Input value={form.requested_by} onChange={e => setForm({...form, requested_by:e.target.value})}/></div>
          {create.isError && <p className="text-sm text-destructive">The idea could not be created. Check for a duplicate name.</p>}
          <Button className="w-full" disabled={create.isPending}>{create.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin"/> : <Plus className="mr-2 h-4 w-4"/>}Create conception</Button>
        </form></CardContent></Card>
      <div className="space-y-6"><Card><CardHeader><CardTitle className="text-lg">Development requests</CardTitle><CardDescription>Intake and conversion trace for product creation.</CardDescription></CardHeader><CardContent className="space-y-3">
        {requests.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {requests.data?.length === 0 && <p className="text-sm text-muted-foreground">No ideas captured yet.</p>}
        {requests.data?.map(item => <button type="button" key={item.id} onClick={()=>{setSelectedProduct(item.product_id);setDelivery(value=>({...value,project_name:item.title}));}} className={`w-full rounded-lg border p-4 text-left ${selectedProduct===item.product_id?"border-primary bg-primary/5":""}`}>
          <div className="flex flex-wrap items-start justify-between gap-2"><div><p className="font-medium">{item.title}</p><p className="mt-1 text-sm text-muted-foreground">{item.description}</p></div><Badge variant="outline">{item.status}</Badge></div>
          <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground"><span>{item.requested_by || "system"} · {item.priority}</span><Link className="text-primary hover:underline" to={`/system-map?product=${item.product_id}`}>Open System Map</Link></div>
        </button>)}
      </CardContent></Card>
      {concept.data && <Card><CardHeader><div className="flex items-center justify-between gap-3"><div><CardTitle className="text-lg">Concept decision</CardTitle><CardDescription>Execution remains blocked until concept and map are approved.</CardDescription></div><Badge variant="outline">{concept.data.concept.status}</Badge></div></CardHeader><CardContent className="space-y-4">
        <div className="rounded-md bg-muted/40 p-3 text-sm"><p className="font-medium">{concept.data.current_revision?.problem_statement}</p><p className="mt-1 text-muted-foreground">{concept.data.current_revision?.vision}</p></div>
        <div className="flex flex-wrap gap-2"><Link to={`/system-map?product=${selectedProduct}`}><Button variant="outline">Review System Map</Button></Link>
          {["draft","rework"].includes(concept.data.concept.status) && <Button onClick={()=>submitConcept.mutate(concept.data!.concept.id)} disabled={submitConcept.isPending}>Submit for review</Button>}
          {concept.data.concept.status==="in_review" && <Link to="/governance"><Button>Open approval inbox</Button></Link>}
        </div>
        {submitConcept.isError && <p className="text-sm text-destructive">Submission was blocked. Validate the System Map and your command permission.</p>}
        {concept.data.concept.status==="approved" && <form className="grid gap-3 rounded-lg border p-4 md:grid-cols-3" onSubmit={async e=>{e.preventDefault();await authorize.mutateAsync({conceptId:concept.data!.concept.id,...delivery});}}><div><Label>Version</Label><Input required value={delivery.version} onChange={e=>setDelivery({...delivery,version:e.target.value})}/></div><div><Label>Project name</Label><Input required value={delivery.project_name} onChange={e=>setDelivery({...delivery,project_name:e.target.value})}/></div><div><Label>Owner</Label><Input value={delivery.owner} onChange={e=>setDelivery({...delivery,owner:e.target.value})}/></div><div className="md:col-span-3 flex items-center gap-3"><Button disabled={authorize.isPending}>{authorize.isPending&&<Loader2 className="mr-2 h-4 w-4 animate-spin"/>}Authorize delivery planning</Button>{authorize.data&&<Link className="text-sm text-primary hover:underline" to={`/project-scope`}>Open created Project Scope</Link>}</div></form>}
      </CardContent></Card>}
      </div>
    </div>
  </div>;
}
