/** Backend classifications are facts to display, never client-side permission decisions. */
export const MESSAGE_LABELS = [
  "analysis_pending", "authorization_pending", "decision_pending", "awaiting_executor",
  "quota_unavailable", "executor_busy", "executor_unavailable", "executor_unassigned",
  "awaiting_information", "awaiting_dependency", "awaiting_service", "scheduled", "ready",
  "running", "awaiting_verification", "uncertain_execution", "needs_correction", "delivery_verified",
  "completed", "archived", "possible_duplicate", "possible_obsolete", "obsolete", "informational_feedback", "missing_context",
] as const;
export type MessageLabel = typeof MESSAGE_LABELS[number];
const known = new Set<string>(MESSAGE_LABELS);
export function visibleMessageLabels(labels: readonly string[] = []): MessageLabel[] {
  return [...new Set(labels)].filter((label): label is MessageLabel => known.has(label)).slice(0, 3);
}
export const MESSAGE_LABEL_GROUPS = {
  incoming: ["analysis_pending", "missing_context", "authorization_pending", "decision_pending"],
  outgoing: ["analysis_pending", "ready", "scheduled", "authorization_pending", "decision_pending"],
  incubations: ["analysis_pending", "decision_pending", "awaiting_information", "awaiting_dependency", "possible_obsolete"],
  execution: ["awaiting_executor", "quota_unavailable", "executor_busy", "executor_unavailable", "executor_unassigned", "awaiting_information", "awaiting_dependency", "awaiting_service", "scheduled", "ready", "running", "awaiting_verification", "uncertain_execution", "needs_correction"],
  completed: ["delivery_verified", "completed", "informational_feedback"],
  archived: ["archived", "obsolete", "possible_duplicate", "possible_obsolete", "informational_feedback"],
} satisfies Record<string, MessageLabel[]>;

export function operatorDestination(item: {
  operator_destination?: string | null; operator_decision?: string | null; operator_question_id?: string | null;
}): string | null {
  if (!["authorization", "question"].includes(item.operator_decision ?? "")) return null;
  const question = item.operator_decision === "question" && item.operator_question_id
    ? `&questionId=${encodeURIComponent(item.operator_question_id)}` : "";
  switch (item.operator_destination) {
    case "agent_tasks": return `/personal?tab=agent-work&workGroup=tasks&workView=decision${question}`;
    case "incubations": return `/personal?tab=agent-work&workGroup=incubation&incubationView=decision${question}`;
    case "moodle_approvals": return `/personal?tab=agent-work&workGroup=moodle${question}`;
    default: return null;
  }
}
