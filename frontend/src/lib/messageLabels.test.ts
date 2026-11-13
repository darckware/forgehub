import { describe, expect, it } from "vitest";
import { MESSAGE_LABELS, visibleMessageLabels, operatorDestination } from "./messageLabels";
import type { Demand } from "@/hooks/useDemands";
import pt from "@/i18n/locales/pt-BR/demands.json";
import en from "@/i18n/locales/en/demands.json";
import es from "@/i18n/locales/es/demands.json";

describe("automatic message labels", () => {
  it("renders only known, unique labels and caps each message at three", () => {
    expect(visibleMessageLabels(["awaiting_executor", "quota_unavailable", "awaiting_executor", "unknown", "scheduled", "ready"])).toEqual(["awaiting_executor", "quota_unavailable", "scheduled"]);
  });
  it("keeps archived history distinct from a completed delivery", () => {
    expect(visibleMessageLabels(["archived"])).toEqual(["archived"]);
    expect(pt.messageLabels.items.archived.label).toBe("Arquivada");
    expect(pt.messageLabels.items.completed.label).toBe("Concluída");
  });
  it("has a label and explanation in every supported locale", () => {
    for (const locale of [pt, en, es]) for (const key of MESSAGE_LABELS) {
      expect(locale.messageLabels.items[key].label).toBeTruthy();
      expect(locale.messageLabels.items[key].description).toBeTruthy();
    }
  });
  it("links genuine authorization and question decisions to their owning tab", () => {
    const row = { operator_destination: "agent_tasks", operator_decision: "authorization", operator_question_id: null } as Demand;
    expect(operatorDestination(row)).toBe("/personal?tab=agent-work&workTab=approvals");
    expect(operatorDestination({ ...row, operator_destination: "incubations" })).toBe("/personal?tab=agent-work&workTab=incubation&incubationView=decision");
    expect(operatorDestination({ ...row, operator_destination: "moodle_approvals" })).toBe("/personal?tab=agent-work&workTab=approvals");
    const question = { ...row, operator_decision: "question" as const, operator_question_id: "question-42" };
    expect(operatorDestination(question)).toBe("/personal?tab=agent-work&workTab=answers&questionId=question-42");
    expect(operatorDestination({ ...question, operator_destination: "incubations" })).toContain("workTab=answers&questionId=question-42");
    expect(operatorDestination({ ...row, operator_decision: null })).toBeNull();
  });
  it("links failures that only a person can move forward to Aprovações", () => {
    const row = { operator_destination: "agent_tasks", operator_decision: "correction", operator_question_id: null } as Demand;
    expect(operatorDestination(row)).toBe("/personal?tab=agent-work&workTab=approvals");
    expect(operatorDestination({ ...row, operator_decision: "reconciliation" })).toBe("/personal?tab=agent-work&workTab=approvals");
  });
});
