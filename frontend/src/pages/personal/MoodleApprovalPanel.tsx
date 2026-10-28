import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useAgents, useStreamTelegramImprovePrompt } from "@/hooks/useAgent";
import { ImprovePromptDialog } from "@/components/chat/ImprovePromptDialog";
import { Sparkles } from "lucide-react";
import { ApiError, apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

type Approval = { request_id: string; message_id: string; number: number; summary: string; operation: string; environment: string; host: string; params: unknown; destructive: boolean; params_hash: string; message_updated_at: string; expires_at: string };
const endpoint = "/api/v1/personal/moodle-approvals";
const key = ["personal", "moodle-approvals"];

export function MoodleApprovalPanel() {
  const { t } = useTranslation("personal");
  const agents = useAgents();
  const athos = agents.data?.find(a => a.profile_slug?.toLowerCase() === "athos" || a.name.trim().toLowerCase() === "athos");
  const improvePrompt = useStreamTelegramImprovePrompt(athos?.id ?? "");
  const [improveOpen, setImproveOpen] = useState(false);
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: key, queryFn: () => apiClient.get<{ items: Approval[] }>(endpoint) });
  const [challenge, setChallenge] = useState("");
  const [linkBusy, setLinkBusy] = useState(false);
  const [linkStatus, setLinkStatus] = useState<"sent" | "error" | null>(null);
  useEffect(() => {
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const value = fragment.get("telegram_challenge");
    if (value) {
      setChallenge(value);
      fragment.delete("telegram_challenge");
      const hash = fragment.toString();
      window.history.replaceState(window.history.state, "", `${window.location.pathname}${window.location.search}${hash ? `#${hash}` : ""}`);
    }
  }, []);
  async function requestLink() {
    if (linkBusy) return;
    setLinkBusy(true); setLinkStatus(null);
    try { await apiClient.post(`${endpoint}/telegram-challenge`); setLinkStatus("sent"); }
    catch { setLinkStatus("error"); }
    finally { setLinkBusy(false); }
  }
  const [selected, setSelected] = useState<string[]>([]);
  const [executor, setExecutor] = useState<string | null>(null);
  const [instruction, setInstruction] = useState("");
  const [password, setPassword] = useState("");
  const [reveal, setReveal] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [error, setError] = useState(false);
  const [success, setSuccess] = useState(false);
  const agentId = executor ?? agents.data?.find(a => a.profile_slug?.toLowerCase() === "maia" || a.name.toLowerCase() === "maia")?.id ?? "";
  const items = Array.isArray(query.data?.items) ? query.data.items : [];
  const chosen = items.filter(item => selected.includes(item.request_id));
  const clearSecret = () => { setPassword(""); setReveal(false); };
  async function authorize() {
    if (busyRef.current || !password || !challenge || !agentId || !chosen.length) return;
    busyRef.current = true; setBusy(true); setError(false);
    const payload = { password, telegram_challenge: challenge, executor_agent_id: agentId, instruction, items: chosen.map(({ request_id, message_id, params_hash, message_updated_at }) => ({ request_id, message_id, params_hash, message_updated_at })) };
    clearSecret(); setChallenge("");
    try {
      await apiClient.post<{ approved: number[] }>(`${endpoint}/authorize`, payload);
      setSelected([]); setInstruction(""); setSuccess(true); setConfirming(false);
      void queryClient.invalidateQueries({ queryKey: key });
    } catch { setError(true); setConfirming(false); }
    finally { busyRef.current = false; setBusy(false); }
  }
  if (query.error instanceof ApiError && [404, 503].includes(query.error.status)) return null;
  return <section className="space-y-3 rounded-md border p-4" aria-label={t("moodleApproval.title")}>
    <h3 className="font-semibold">{t("moodleApproval.title")}</h3>
    <p className="text-sm text-muted-foreground">{t("moodleApproval.hint")}</p>
    {query.isLoading && <p role="status">{t("moodleApproval.loading")}</p>}
    {query.isError && <div role="alert"><p>{t("moodleApproval.loadError")}</p><Button variant="outline" onClick={() => void query.refetch()}>{t("moodleApproval.retry")}</Button></div>}
    {!query.isLoading && !query.isError && !items.length && <p className="text-sm">{t("moodleApproval.empty")}</p>}
    <div className="space-y-2"><p className="text-sm">{t("moodleApproval.sessionHint")}</p><p className="text-sm">{t(challenge ? "moodleApproval.challengeReady" : "moodleApproval.challengeNeeded")}</p>
      <Button type="button" variant="outline" size="sm" disabled={linkBusy} onClick={() => void requestLink()}>{t("moodleApproval.requestLink")}</Button>
      {linkStatus && <p role={linkStatus === "error" ? "alert" : "status"} className="text-sm">{t(linkStatus === "error" ? "moodleApproval.linkError" : "moodleApproval.linkSent")}</p>}</div>
    {items.length > 0 && <>
      <ul className="max-h-96 space-y-2 overflow-auto">{items.map(item => <li key={item.request_id} className="rounded-md border p-3 text-sm">
        <label className="flex gap-2"><input type="checkbox" aria-label={t("moodleApproval.select", { number: item.number })} checked={selected.includes(item.request_id)} disabled={busy} onChange={e => setSelected(ids => e.target.checked ? [...ids, item.request_id] : ids.filter(id => id !== item.request_id))} /><span><strong>#{item.number} · {item.summary}</strong><span className="block">{t("moodleApproval.operation")}: {item.operation} · {t("moodleApproval.environment")}: {item.environment} · {item.destructive ? t("moodleApproval.destructive") : t("moodleApproval.nonDestructive")}</span></span></label>
      </li>)}</ul>
      <label className="block space-y-1 text-sm">{t("moodleApproval.executor")}<Select value={agentId} disabled={busy} onChange={e => setExecutor(e.target.value)}><option value="">{t("moodleApproval.chooseAgent")}</option>{(agents.data ?? []).map(agent => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</Select></label>
      <p className="text-xs text-muted-foreground">{t("moodleApproval.executorAccessHint")}</p>
      {agents.isError && <p role="alert">{t("moodleApproval.agentsError")}</p>}
      <label className="block space-y-1 text-sm">{t("moodleApproval.instruction")}<Textarea className="resize-none" rows={3} value={instruction} disabled={busy} onChange={e => setInstruction(e.target.value)} /></label>
      <Button type="button" variant="ghost" size="icon" disabled={!athos || busy} aria-label={t("moodleApproval.improve")} title={t("moodleApproval.improve")} onClick={() => setImproveOpen(true)}><Sparkles className="h-4 w-4" /></Button>
      <div><Button disabled={!chosen.length || !agentId || !challenge || busy} onClick={() => { setError(false); setSuccess(false); setConfirming(true); }}>{t("moodleApproval.review")}</Button></div>
    </>}
    {error && <p role="alert" className="text-sm text-destructive">{t("moodleApproval.error")}</p>}
    {success && <p role="status" className="text-sm">{t("moodleApproval.success")}</p>}
    {improveOpen && athos && <ImprovePromptDialog initialDraft={instruction} subject={athos.name} agents={agents.data ?? []} includeLocalSlashCommands={false} includeHermesSlashCommands={false} improvePrompt={improvePrompt} onApply={text => { setInstruction(text); setImproveOpen(false); }} onClose={() => setImproveOpen(false)} />}
    <ConfirmDialog open={confirming} title={t("moodleApproval.confirmTitle")} description={t("moodleApproval.confirmHint")} confirmLabel={t("moodleApproval.confirm")} variant={chosen.some(item => item.destructive) ? "destructive" : "default"} loading={busy} dismissDisabled={busy} confirmDisabled={!password || !challenge} onConfirm={() => void authorize()} onCancel={() => { if (!busy) { clearSecret(); setConfirming(false); } }}>
      <ul className="max-h-64 space-y-2 overflow-auto text-sm">{chosen.map(item => <li key={item.request_id}>#{item.number} · {item.summary} · {item.operation} · {item.environment} · {item.destructive ? t("moodleApproval.destructive") : t("moodleApproval.nonDestructive")}<p className="break-all">{t("moodleApproval.host")}: {item.host}</p><pre className="whitespace-pre-wrap break-all">{t("moodleApproval.params")}: {JSON.stringify(item.params, null, 2)}</pre></li>)}</ul>
      <p className="mt-2 text-sm">{t("moodleApproval.executor")}: {(agents.data ?? []).find(agent => agent.id === agentId)?.name}</p>
      {instruction && <p className="mt-2 whitespace-pre-wrap break-words text-sm">{t("moodleApproval.instruction")}: {instruction}</p>}
      <label className="block space-y-1 text-sm">{t("moodleApproval.password")}<Input type={reveal ? "text" : "password"} autoComplete="current-password" value={password} disabled={busy} onChange={e => setPassword(e.target.value)} /></label>
      <Button type="button" variant="outline" size="sm" aria-pressed={reveal} onClick={() => setReveal(!reveal)}>{t(reveal ? "moodleApproval.hidePassword" : "moodleApproval.showPassword")}</Button>

    </ConfirmDialog>
  </section>;
}
