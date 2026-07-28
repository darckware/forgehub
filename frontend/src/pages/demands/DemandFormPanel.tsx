import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, Paperclip, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuthStore } from "@/store/authStore";
import {
  useCreateDemand,
  useUpdateDemand,
  useUploadDemandAttachment,
  type Demand,
} from "@/hooks/useDemands";
import { useAgents } from "@/hooks/useAgent";
import { useProjects } from "@/hooks/useProject";
import { useTasks } from "@/hooks/useTask";

/** Mandatory, always one of these two (2026-07-28) -- never "none"/"demand".
 * "backlog" é trabalho estacionado: classificação, não vínculo -- nunca
 * carrega origin_id e nunca dispara (ver DEMAND_ORIGIN_TYPES no backend).
 * Vira "task" pelo botão Promover a Task, no painel de leitura. */
type OriginChoice = "task" | "backlog";

/** ISO datetime -> `<input type="datetime-local">` value (local time, no
 * timezone suffix -- that's what the input expects and what `new
 * Date(...)` parses a bare "YYYY-MM-DDTHH:mm" string back as). */
function isoToDatetimeLocal(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** ISO datetime -> a plain locale string for the disabled Task execution
 * display, or "" (falls back to the field's placeholder) before it's been
 * stamped. */
function formatExecutionAt(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString();
}

/** Rótulo i18n do ciclo de vida do despacho (`dispatch_status`), exibido no
 * campo Status. Não é coluna nova: o backend já grava exatamente estes
 * quatro valores (ver DEMAND_DISPATCH_STATUSES) -- até 2026-07-26 eles só
 * apareciam como faixa colorida no painel de leitura, nunca como um campo
 * legível do formulário. "pending" está na tupla do modelo mas nenhum
 * caminho do backend o escreve, por isso não tem rótulo aqui. */
const DISPATCH_STATUS_LABEL: Record<string, string> = {
  dispatched: "form.statusDispatched",
  running: "form.statusRunning",
  failed: "form.statusFailed",
  completed: "form.statusCompleted",
};

/**
 * "Nova nota" / "Alterar" -- a side panel (not a modal), inline in the same
 * slot the reading pane normally occupies, per Marcelo's mailbox/internal-
 * email framing: composing or editing a message opens on the right, same
 * as reading one does. Handles both create (no `demand` prop) and edit
 * (prefilled from an existing `demand`) in one form, since the fields are
 * identical either way -- Scheduled send, From (agent), To (target agent),
 * Tipo (formerly "Origem"/Origin -- reply-to a Task or another message, by
 * its display number; see isIncoming below for why it's labeled
 * differently depending on direction), Retorno (does this message expect a
 * response back), Subject, Body, Attachments.
 *
 * From (agent) picks a real registered Agent as the sender instead of
 * defaulting to "admin" (see DemandSubmitIn/DemandUpdateIn.from_agent_id) --
 * editable in both compose and edit mode, e.g. to fix up a message that
 * arrived with no sender agent on file. Together with Retorno=Yes, it
 * completes an agent-to-agent relay: the To agent executes the prompt, and
 * once its run finishes, get_dispatch_status routes the reply's
 * target_agent_id back to this demand's from_agent_id -- the requester --
 * instead of leaving it generic. With no From agent picked, requires_response
 * still marks the item (the "AR" badge), there's just nobody to relay to.
 *
 * Tipo itself is required on compose (not edit -- see handleSubmit), and
 * defaults to Task there (the dominant case) with Send at defaulted to
 * now -- both pre-filled so the target agent (autofocused on open) is the
 * one thing left to fill in before Send is enabled. Edit mode never
 * applies these defaults, it always reflects the existing demand's actual
 * values. Two things become mandatory together: Tipo=Task requires a
 * target agent (there's no point linking to a task with nobody to act on
 * it), and setting a scheduled send time requires one too (the background
 * loop needs to know who to dispatch to once it fires -- see
 * AgentDemand.scheduled_at's docstring backend-side).
 *
 * The disabled "Execução" field shows AgentDemand.task_execution_at --
 * when the work this message stands for actually finished running. Shown
 * for Tipo=Task and for any message that was dispatched at all (2026-07-25:
 * it used to be Tipo=Task only, which meant a dispatched-executed-replied
 * message still read as empty, since the column only had task.py's
 * linked-ProjectTask writer back then and most messages link no task).
 * Now demand.py's get_dispatch_status stamps it on either terminal run
 * outcome too -- see AgentDemand.task_execution_at's docstring for both
 * writers. Empty means it genuinely never ran; never editable here.
 *
 * New-item routing in the sidebar tree (create only, not edit): Tipo=Task
 * counts as Outbox even for a human-composed item with no from_agent_id
 * (see DemandsPage's SelectedFolder docstring); Tipo=Note is filed
 * straight into Notes/Archived (status="archived" sent on create); replies
 * land in Incoming on their own, already, since get_dispatch_status's reply
 * row never sets target_agent_id.
 *
 * The disabled "ID" field (next to Send at) is this message's own number --
 * AgentDemand.number, the server-assigned IDENTITY column shown in the list
 * and in the reading pane's header. Empty while composing, since the number
 * only exists once the message is saved. It used to render the *linked
 * origin's* number instead (2026-07-26 change): that read as permanently
 * blank in practice, because origin_id is only ever set by an API caller
 * that passes origin_number and this form has no picker for it -- so the
 * field showed nothing even on messages that clearly had an ID everywhere
 * else in the UI.
 *
 * The origin link itself is still round-tripped on save (see
 * linkedOriginNumber below and handleSubmit) so editing a message doesn't
 * silently drop an existing Task/Note link -- it just isn't what the ID
 * field displays. Tipo (None/Task/Note, stored as `origin_type` -- unrenamed
 * backend-side, only the label changed) stays selectable and is sent with no
 * number, which the backend accepts (see demand.py's _resolve_origin: a
 * category-only origin, no specific link yet).
 *
 * `subject`/`body` stay controlled (lifted to DemandsPage) rather than
 * local state -- DemandsPage registers them as an AssistantForm while this
 * panel is open, so the assistant can fill them on request.
 */
export function DemandFormPanel({
  demand,
  subject,
  onSubjectChange,
  body,
  onBodyChange,
  onClose,
}: {
  /** Present in edit mode, undefined when composing a new message. */
  demand?: Demand;
  subject: string;
  onSubjectChange: (value: string) => void;
  body: string;
  onBodyChange: (value: string) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation("demands");
  const user = useAuthStore((s) => s.user);
  const { data: agents } = useAgents();
  const { data: projects } = useProjects();
  // File + its caption travel together: the description is per file, so
  // keeping two parallel arrays would drift the moment one is removed.
  const [files, setFiles] = useState<{ file: File; description: string }[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const agentSelectRef = useRef<HTMLSelectElement>(null);
  const createDemand = useCreateDemand();
  const updateDemand = useUpdateDemand();
  const uploadAttachment = useUploadDemandAttachment();
  const [error, setError] = useState<string | null>(null);

  const isEdit = demand !== undefined;
  // "Tipo" (formerly "Origem") reads as two different things depending on
  // direction, even though it's the same stored origin_type -- composing
  // is always Outgoing (you're the sender: Task = "dispatch this",
  // Note = "just an FYI, no dispatch"); editing an item that arrived FROM
  // a registered agent is Incoming (Task = "process this and reply if
  // Retorno=Yes", Note = "just read, never process"). from_agent_id set
  // is what makes it Incoming -- a real agent sent it in, as opposed to
  // Marcelo having composed it himself.
  const isIncoming = isEdit && demand?.from_agent_id != null;

  const [targetAgentId, setTargetAgentId] = useState(demand?.target_agent_id ?? "");
  // "From (agent)" -- shown and editable in both compose and edit mode
  // (DemandUpdateIn.from_agent_id lets "Alterar" fix up a message that
  // arrived with no sender agent on file). Lets the requester's identity be
  // a real registered Agent instead of defaulting to "admin", which the
  // Return relay below needs: with no From agent on file, a reply has
  // nobody to route back to.
  const [fromAgentId, setFromAgentId] = useState(demand?.from_agent_id ?? "");
  // Which project this message is about -- classification only, see
  // AgentDemand.project_id's docstring backend-side (independent of the
  // convert flow's own project picker).
  const [projectId, setProjectId] = useState(demand?.project_id ?? "");
  // Compose defaults to Origin=Task (the dominant case, and Origin is
  // required on compose anyway -- see handleSubmit) with Send at defaulted
  // to now (adjust it to schedule for later instead). Edit mode always
  // reflects the existing demand's actual values.
  const [originChoice, setOriginChoice] = useState<OriginChoice>(() => {
    const atual = demand?.origin_type;
    if (atual === "task" || atual === "backlog") return atual;
    // Compose never preselects an agent (nothing to default From to), so
    // Tipo can't start as Task -- see hasAgent below, same rule that keeps
    // the option itself off the list until an agent is picked. Mandatory
    // field (2026-07-28): always a real value, backlog is the safe default.
    return "backlog";
  });
  // Display-only, derived straight from `demand` rather than state -- see
  // this file's docstring. origin_id is a ProjectTask.id for Tipo=Task
  // (see AgentDemand.origin_id's docstring backend-side) -- not a display
  // number on its own, so resolving it to something showable means finding
  // that row in the tasks list. Also what gets resent on save (see
  // handleSubmit) -- if an edit never resent the existing link, saving
  // would silently drop it on every save (the PATCH always includes
  // origin_type, so the backend's _resolve_origin always runs and would
  // treat a missing origin_number as "clear it").
  const { data: allTasksForOriginLookup } = useTasks();
  const linkedOriginNumber =
    demand?.origin_type === "task" && demand?.origin_id
      ? allTasksForOriginLookup?.find((t) => t.id === demand.origin_id)?.number
      : undefined;
  // "ID" mostra o número da PRÓPRIA mensagem (#613), não o da origem
  // vinculada (2026-07-26). O número é server-assigned (AgentDemand.number,
  // coluna IDENTITY) e já aparece na lista e no cabeçalho do painel de
  // leitura -- não aparecer aqui fazia o campo ficar permanentemente vazio,
  // já que origin_id só é preenchido por um caller de API que envie
  // origin_number, e o formulário nunca teve seletor para isso. Em modo de
  // composição fica vazio de propósito: o número só existe depois do envio.
  const originIdDisplay = isEdit && demand?.number != null ? String(demand.number) : "";
  // "Retorno" -- whether completing a dispatched Task creates a real return
  // message back to the sender, instead of only recording the result on
  // this same message (2026-07-28, Marcelo: "preciso gerar... uma mensagem
  // de retorno quando solicitado pelo agente... e o padrão é não").
  const [requiresResponse, setRequiresResponse] = useState(demand?.requires_response ?? false);
  const [scheduledAt, setScheduledAt] = useState(
    isoToDatetimeLocal(demand?.scheduled_at ?? (isEdit ? demand?.created_at : new Date().toISOString()))
  );
  // True only when there's no real scheduled_at and the field is just
  // showing the item's creation date as a readable fallback (e.g. an
  // auto-created reply note, which never goes through the "Send at"
  // scheduling flow) -- must never be resent as a real schedule just
  // because the field isn't blank; see handleSubmit's scheduledAtIso.
  const isScheduledAtFallback = isEdit && !demand?.scheduled_at;
  // Uma mensagem já despachada teve seu envio *acontecido* -- "Send at"
  // vira registro histórico, não um controle (2026-07-26). O loop agendado
  // só pega itens com dispatch_status NULL, então reescrever a hora não
  // reenviaria nada: só falsificaria quando a mensagem de fato saiu. O
  // backend recusa a alteração (update_demand), aqui o campo fica desabilitado
  // para que isso não pareça editável em primeiro lugar.
  const alreadyDispatched = isEdit && demand?.dispatch_status != null;

  // Origin=Task and Send at both make target_agent_id required (see
  // handleSubmit) -- pull focus straight to it on compose so that's the
  // first thing filled in.
  useEffect(() => {
    if (!isEdit) agentSelectRef.current?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A validation error from a previous Send attempt otherwise stays on
  // screen after the user fixes the field it complained about -- clear it
  // on any change to any field, not just on re-submit.
  useEffect(() => {
    setError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetAgentId, fromAgentId, projectId, originChoice, requiresResponse, scheduledAt, subject, body]);

  // Task sem De (From) nem chega a existir como opção (2026-07-28, Marcelo:
  // "se o agente não tem (to), não tem retorno. Preciso ter agente (from)
  // no tipo task. Isso é regra") -- De é o agente âncora: "Para" em branco
  // já significa "o próprio remetente executa" (effectiveTargetAgentId
  // abaixo), então De sozinho é suficiente para preencher os dois lados;
  // To sozinho não é (uma Task endereçada sem remetente não tem a quem o
  // resultado pertence). Espelha o rebaixamento que o backend já faz
  // (_reconcile_task_origin), só que proativo: o formulário nunca deixa o
  // operador chegar a montar essa combinação inválida.
  const hasAgent = Boolean(fromAgentId);
  useEffect(() => {
    if (!hasAgent && originChoice === "task") setOriginChoice("backlog");
  }, [hasAgent, originChoice]);

  // Trocar De para o agente que já estava em Para (ou vice-versa, via edição
  // de um item antigo salvo antes desta regra) deixaria os dois iguais --
  // volta Para para "em branco" (o próprio remetente) em vez de deixar a
  // combinação redundante em pé, já que a opção correspondente acabou de
  // sumir da lista logo acima.
  useEffect(() => {
    if (targetAgentId && targetAgentId === fromAgentId) setTargetAgentId("");
  }, [fromAgentId, targetAgentId]);

  /** Tipos que realmente colocam trabalho em movimento. Só Task dispara:
   * Backlog é trabalho estacionado e Nota é FYI, então nenhum dos dois
   * precisa de destinatário nem de horário de envio. */
  const dispatches = originChoice === "task";

  const isPending = createDemand.isPending || updateDemand.isPending || uploadAttachment.isPending;
  const canSubmit = subject.trim().length > 0 && body.trim().length > 0 && !isPending;

  async function handleSubmit() {
    setError(null);
    // De/Para inverteram a obrigatoriedade em 2026-07-26. Toda mensagem
    // pertence a um agente -- é dele a fila --, então **From** é o campo
    // obrigatório. **To** deixou de ser: em branco significa "para mim
    // mesmo", o caso de um agente registrando a própria tarefa; preenchê-lo
    // é que passa o trabalho adiante. Antes era o contrário (To obrigatório
    // para Tipo=Task, From opcional), o que tornava impossível expressar
    // uma tarefa que o agente executa para si.
    if (!isEdit && !fromAgentId) {
      setError(t("form.fromAgentRequired"));
      return;
    }
    // Never user-entered (see linkedOriginNumber's docstring) -- resent
    // as-is so an edit doesn't drop an existing Task/Note link just
    // because the currently selected Tipo matches what was already saved.
    // Switching Tipo in this same edit (e.g. Task -> Note) has nothing to
    // resend for the new choice, since there's no UI to pick a different
    // link -- that's fine, it just clears the number, matching "this
    // field isn't editable here".
    const parsedOriginNumber = originChoice === "task" ? linkedOriginNumber : undefined;
    const scheduledAtIso = !dispatches
      ? // Backlog e Nota não disparam -- mandar um horário de envio para
        // eles só encheria a coluna de um agendamento que nenhum loop vai
        // honrar (run_scheduled_dispatch_pass exige target_agent_id).
        undefined
      : alreadyDispatched
      ? // Nunca reenviado numa mensagem já despachada: o backend recusa
        // alterar (update_demand), e mesmo um "mesmo valor" seria recusado --
        // <input type="datetime-local"> só tem precisão de minuto, então o
        // round-trip perde os segundos do scheduled_at original e chegaria
        // lá como um valor diferente, quebrando qualquer edição de
        // assunto/corpo nessas mensagens.
        undefined
      : isScheduledAtFallback && scheduledAt === isoToDatetimeLocal(demand?.created_at)
        ? undefined // untouched fallback display -- nothing to send, keep it null
        : scheduledAt
          ? new Date(scheduledAt).toISOString()
          : isEdit && demand?.scheduled_at
            ? null
            : undefined;
    // "To" em branco = para o próprio remetente. Resolvido aqui, na
    // composição, e não no backend: assim a linha gravada diz explicitamente
    // a quem a tarefa pertence, em vez de deixar um NULL que cada consumidor
    // (árvore de pastas, loop de despacho, relay de Retorno) teria que
    // reinterpretar por conta própria -- e o loop agendado só despacha o que
    // tem target_agent_id, então uma tarefa para si mesma nunca rodaria.
    // Só para Tipos que disparam; Backlog fica sem destinatário mesmo.
    const effectiveTargetAgentId = dispatches ? targetAgentId || fromAgentId : targetAgentId;
    try {
      if (isEdit) {
        await updateDemand.mutateAsync({
          id: demand.id,
          subject,
          body,
          targetAgentId: effectiveTargetAgentId || null,
          fromAgentId: fromAgentId || null,
          projectId: projectId || null,
          originType: originChoice,
          originNumber: parsedOriginNumber,
          requiresResponse,
          scheduledAt: scheduledAtIso,
        });
        for (const { file, description } of files) {
          await uploadAttachment.mutateAsync({ demandId: demand.id, file, description });
        }
      } else {
        const fromAgent = (agents ?? []).find((a) => a.id === fromAgentId);
        const created = await createDemand.mutateAsync({
          from_agent: fromAgent?.name ?? user?.username ?? "admin",
          fromAgentId: fromAgentId || undefined,
          subject,
          body,
          targetAgentId: effectiveTargetAgentId || undefined,
          projectId: projectId || undefined,
          originType: originChoice,
          originNumber: parsedOriginNumber,
          requiresResponse,
          scheduledAt: scheduledAtIso ?? undefined,
          // Sem arquivamento automático na criação: isso existia só para o
          // Tipo=Nota, que ia direto para Arquivadas, e saiu junto com ele
          // (2026-07-26). Task e Backlog nascem em Incoming; arquivar passou
          // a ser sempre uma ação explícita (botão Archive ou arrastar para
          // uma pasta).
        });
        for (const { file, description } of files) {
          await uploadAttachment.mutateAsync({ demandId: created.id, file, description });
        }
      }
      onClose();
    } catch (e) {
      setError((e as Error)?.message ?? "Failed to save");
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col border-l border-border/60">
      <div className="shrink-0 border-b border-border/60 px-5 py-4">
        <h2 className="text-base font-semibold">{isEdit ? t("editTitle") : t("newNoteTitle")}</h2>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-4">
        <div className="flex items-end gap-2">
          {/* Escondido para Backlog/Nota: não disparam, então um horário de
              envio ali seria um controle sem efeito. */}
          {dispatches && (
            <div className="w-56 space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">{t("form.scheduledAt")}</label>
              <Input
                type="datetime-local"
                value={scheduledAt}
                disabled={alreadyDispatched}
                onChange={(e) => setScheduledAt(e.target.value)}
              />
            </div>
          )}
          <div className="w-20 space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">{t("form.originId")}</label>
            <Input disabled value={originIdDisplay} placeholder="#" />
          </div>
          <div className="flex-1 space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">
              {t("form.fromAgent")} <span className="text-destructive">*</span>
            </label>
            <Select ref={agentSelectRef} value={fromAgentId} onChange={(e) => setFromAgentId(e.target.value)}>
              <option value="">{t("form.noFromAgent")}</option>
              {(agents ?? []).map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex-1 space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">{t("form.toAgent")}</label>
            <Select value={targetAgentId} onChange={(e) => setTargetAgentId(e.target.value)}>
              {/* Em branco = para o próprio remetente (ver
                  effectiveTargetAgentId em handleSubmit), então o rótulo
                  precisa dizer isso -- "Nenhum agente" faria parecer que a
                  mensagem não vai a lugar nenhum. */}
              <option value="">{t(dispatches ? "form.toAgentSelf" : "form.noAgent")}</option>
              {/* O próprio De some da lista (2026-07-27, Marcelo: "não faz
                  sentido colocar o mesmo agente (from) e (to) ... quando
                  escolher um agente do from ele será filtrado no to") --
                  redundante escolher explicitamente o mesmo agente nos
                  dois campos quando o Para em branco já significa isso. */}
              {(agents ?? [])
                .filter((agent) => agent.id !== fromAgentId)
                .map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name}
                  </option>
                ))}
            </Select>
          </div>
        </div>

        <div className="flex items-end gap-2">
          <div className="flex-1 space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">{t("form.project")}</label>
            <Select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">{t("form.noProject")}</option>
              {(projects ?? []).map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex-1 space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">{t("form.type")}</label>
            <Select value={originChoice} onChange={(e) => setOriginChoice(e.target.value as OriginChoice)}>
              {/* Só aparece com um agente escolhido (De ou Para) -- ver
                  hasAgent acima. Sem isso o próprio formulário deixaria
                  montar uma Task que o backend rebaixaria a Backlog na
                  hora de salvar. */}
              {hasAgent && (
                <option value="task">{t(isIncoming ? "form.typeTaskIncoming" : "form.typeTaskOutgoing")}</option>
              )}
              <option value="backlog">{t("form.typeBacklog")}</option>
            </Select>
          </div>
          {(originChoice === "task" || Boolean(demand?.dispatch_status)) && (
            <>
              {/* Somente leitura: quem escreve isto é o ciclo de despacho
                  (demand.py), não o operador. Editável, viraria um jeito de
                  declarar "finalizado" algo que nunca rodou. */}
              <div className="w-36 space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">{t("form.status")}</label>
                <Input
                  disabled
                  placeholder="—"
                  value={
                    demand?.dispatch_status && DISPATCH_STATUS_LABEL[demand.dispatch_status]
                      ? t(DISPATCH_STATUS_LABEL[demand.dispatch_status])
                      : ""
                  }
                />
              </div>
              <div className="w-44 space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">{t("form.taskExecutionAt")}</label>
                <Input disabled value={formatExecutionAt(demand?.task_execution_at)} placeholder="—" />
              </div>
            </>
          )}
          {originChoice === "task" && (
            <div className="w-32 space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">{t("form.requiresResponse")}</label>
              <Select
                value={requiresResponse ? "yes" : "no"}
                onChange={(e) => setRequiresResponse(e.target.value === "yes")}
              >
                <option value="no">{t("form.requiresResponseNo")}</option>
                <option value="yes">{t("form.requiresResponseYes")}</option>
              </Select>
            </div>
          )}
        </div>

        <Input
          placeholder={t("subjectPlaceholder")}
          value={subject}
          onChange={(e) => onSubjectChange(e.target.value)}
          maxLength={255}
        />
        <Textarea
          placeholder={t("bodyPlaceholder")}
          value={body}
          onChange={(e) => onBodyChange(e.target.value)}
          rows={12}
        />
        {/* Resultado do processamento -- gravado pelo backend na própria
            mensagem quando o despacho termina (2026-07-28), somente
            leitura. Só existe depois de completar/falhar. */}
        {demand?.dispatch_result && (
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">{t("form.dispatchResult")}</label>
            <Textarea disabled value={demand.dispatch_result} rows={6} />
          </div>
        )}

        <div>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => {
              const picked = Array.from(e.target.files ?? []);
              setFiles((prev) => [...prev, ...picked.map((file) => ({ file, description: "" }))]);
              e.target.value = "";
            }}
          />
          <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={() => fileInputRef.current?.click()}>
            <Paperclip className="h-3.5 w-3.5" /> {t("attachFileButton")}
          </Button>
          {files.length > 0 && (
            <ul className="mt-2 space-y-1.5">
              {files.map((entry, i) => (
                <li
                  key={`${entry.file.name}-${i}`}
                  className="space-y-1 rounded-md bg-muted/40 px-2 py-1.5 text-xs"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate">{entry.file.name}</span>
                    <button
                      type="button"
                      className="shrink-0 text-muted-foreground hover:text-destructive"
                      onClick={() => setFiles((prev) => prev.filter((_, idx) => idx !== i))}
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  {/* Optional per-file caption: the filename alone rarely says
                      what a file is, and once a message carries several
                      attachments the body is the wrong place to explain them. */}
                  <Input
                    className="h-7 text-xs"
                    placeholder={t("attachmentDescriptionPlaceholder")}
                    value={entry.description}
                    maxLength={500}
                    onChange={(e) =>
                      setFiles((prev) =>
                        prev.map((item, idx) =>
                          idx === i ? { ...item, description: e.target.value } : item,
                        ),
                      )
                    }
                  />
                </li>
              ))}
            </ul>
          )}
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}
      </div>

      <div className="flex shrink-0 justify-end gap-3 border-t border-border/60 px-5 py-4">
        <Button variant="outline" onClick={onClose}>
          {t("cancel")}
        </Button>
        <Button disabled={!canSubmit} onClick={handleSubmit} className="min-w-[88px] gap-1.5">
          {isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {t("send")}
        </Button>
      </div>
    </div>
  );
}
