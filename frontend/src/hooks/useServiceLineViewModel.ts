import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";
import { useServiceLines, type ServiceLine } from "@/hooks/useServiceLines";

export const serviceLineFormSchema = z.object({
  slug: z.string().min(1).max(100).regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/),
  name: z.string().min(1).max(255),
  description: z.string(), stages: z.string(), required_documents: z.string(),
  evidence_types: z.string(), default_agents: z.string(),
  sla_hours: z.string().refine((v) => v === "" || /^\d+$/.test(v)),
  darckware_contract_type: z.string(), client_visible: z.boolean(),
});
export type ServiceLineForm = z.infer<typeof serviceLineFormSchema>;
const empty: ServiceLineForm = { slug: "", name: "", description: "", stages: "", required_documents: "", evidence_types: "", default_agents: "", sla_hours: "", darckware_contract_type: "", client_visible: false };
const list = (text: string) => text.split("\n").map((s) => s.trim()).filter(Boolean);

export function useServiceLineViewModel() {
  const lines = useServiceLines();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<ServiceLine | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [pending, setPending] = useState<ServiceLine | null>(null);
  const form = useForm<ServiceLineForm>({ resolver: zodResolver(serviceLineFormSchema), defaultValues: empty });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["service-lines"] });
  const save = useMutation({
    mutationFn: (values: ServiceLineForm) => {
      const payload = { ...values, description: values.description || null,
        stages: list(values.stages), required_documents: list(values.required_documents),
        evidence_types: list(values.evidence_types), default_agents: list(values.default_agents),
        sla_hours: values.sla_hours === "" ? null : Number(values.sla_hours),
        darckware_contract_type: values.darckware_contract_type || null };
      return editing ? apiClient.patch(`/api/v1/service-lines/${editing.id}`, payload) : apiClient.post("/api/v1/service-lines", payload);
    },
    onSuccess: () => { refresh(); setShowForm(false); },
  });
  const deactivate = useMutation({
    mutationFn: (id: string) => apiClient.delete(`/api/v1/service-lines/${id}`),
    onSuccess: () => { refresh(); setPending(null); },
  });
  function edit(line: ServiceLine | null) {
    setEditing(line); save.reset();
    form.reset(line ? { slug: line.slug, name: line.name, description: line.description ?? "",
      stages: line.stages.join("\n"), required_documents: line.required_documents.join("\n"),
      evidence_types: line.evidence_types.join("\n"), default_agents: line.default_agents.join("\n"),
      sla_hours: line.sla_hours == null ? "" : String(line.sla_hours),
      darckware_contract_type: line.darckware_contract_type ?? "", client_visible: line.client_visible } : empty);
    setShowForm(true);
  }
  return { lines, form, save, deactivate, editing, showForm, setShowForm, pending, setPending, edit };
}
