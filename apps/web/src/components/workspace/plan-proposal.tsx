"use client";

import { useState } from "react";
import { useLocale } from "@/components/locale-provider";

export type PlanChoice = { label: string; description: string; recommended: boolean };
export type PlanQuestion = { id: string; text: string; options: PlanChoice[]; allow_other: boolean };
export type PlanLevel = "solo" | "team" | "studio";
export type PlanOption = { id: string; level: PlanLevel; summary: string; agents: number; speed: "fast" | "medium" | "slow"; tradeoffs: string; recommended: boolean; reason: string };
export type PlanProposal = { status: "ready" | "needs_input"; assumptions: string[]; questions: PlanQuestion[]; options: PlanOption[] };
export type ProposalAnswers = { decisions: Array<{ question: string; answer: string }>; level: PlanLevel | null };

import type { JsonRecord } from "@/lib/api";
import { Icon } from "@/components/shell/icons";
import { useWorkspace } from "./workspace-context";

const OTHER = "__other__";

export function recommendedChoice(question: PlanQuestion): string {
  return (question.options.find((option) => option.recommended) ?? question.options[0])?.label ?? "";
}

export function recommendedLevel(proposal: PlanProposal): PlanLevel | null {
  return proposal.options.find((option) => option.recommended)?.level ?? null;
}

/** Questions and ways to build it, with one answer in each group pre-selected as the recommendation. */
export function ProposalCard({ proposal, disabled, onBuild, onSkip }: {
  proposal: PlanProposal;
  disabled: boolean;
  onBuild: (answers: ProposalAnswers) => void;
  onSkip: () => void;
}) {
  const { t } = useLocale();
  const [picked, setPicked] = useState<Record<string, string>>(() => Object.fromEntries(proposal.questions.map((question) => [question.id, recommendedChoice(question)])));
  const [typed, setTyped] = useState<Record<string, string>>({});
  const [level, setLevel] = useState<PlanLevel | null>(() => recommendedLevel(proposal));

  const answerFor = (question: PlanQuestion) => (picked[question.id] === OTHER ? (typed[question.id] ?? "").trim() : picked[question.id] ?? "");
  const decisions = (answer: (question: PlanQuestion) => string) =>
    proposal.questions.map((question) => ({ question: question.text, answer: answer(question) })).filter((item) => item.answer);
  const incomplete = proposal.questions.some((question) => !answerFor(question));

  return <section className="ask-card" aria-label={t("ask.title")}>
    <h3 className="ask-title">{t("ask.title")}</h3>
    {proposal.assumptions.length > 0 && <p className="ask-assumptions">{t("ask.assumptions")}: {proposal.assumptions.join(" · ")}</p>}
    {proposal.questions.map((question) => <fieldset className="ask-group" key={question.id} disabled={disabled}>
      <legend>{question.text}</legend>
      {question.options.map((option) => <label className="ask-choice" key={option.label}>
        <input type="radio" name={`ask-${question.id}`} checked={picked[question.id] === option.label} onChange={() => setPicked((current) => ({ ...current, [question.id]: option.label }))} />
        <span><strong>{option.label}</strong>{option.recommended && <em className="ask-badge">{t("ask.recommended")}</em>}
          {option.description && <small>{option.description}</small>}</span>
      </label>)}
      {question.allow_other && <label className="ask-choice">
        <input type="radio" name={`ask-${question.id}`} checked={picked[question.id] === OTHER} onChange={() => setPicked((current) => ({ ...current, [question.id]: OTHER }))} />
        <span><strong>{t("ask.other")}</strong>
          {picked[question.id] === OTHER && <input className="ask-other" aria-label={t("ask.other")} value={typed[question.id] ?? ""} maxLength={280} autoFocus
            onChange={(event) => setTyped((current) => ({ ...current, [question.id]: event.target.value }))} />}</span>
      </label>}
    </fieldset>)}
    {proposal.options.length > 0 && <fieldset className="ask-group" disabled={disabled}>
      <legend>{t("ask.how")}</legend>
      {proposal.options.map((option) => <label className="ask-choice" key={option.id}>
        <input type="radio" name="ask-level" checked={level === option.level} onChange={() => setLevel(option.level)} />
        <span><strong>{t(`ask.level.${option.level}`)}</strong>{option.recommended && <em className="ask-badge">{t("ask.recommended")}</em>}
          <small>{option.summary}</small>
          <small>{t("ask.facts", { agents: option.agents, speed: t(`ask.speed.${option.speed}`) })}{option.tradeoffs ? ` · ${option.tradeoffs}` : ""}</small>
          {option.recommended && option.reason && <small>{t("ask.why")}: {option.reason}</small>}</span>
      </label>)}
    </fieldset>}
    <div className="ask-actions">
      <button type="button" className="button button-primary" disabled={disabled || incomplete} onClick={() => onBuild({ decisions: decisions(answerFor), level })}>{t("ask.build")}</button>
      <button type="button" className="button button-quiet" disabled={disabled}
        onClick={() => onBuild({ decisions: decisions(recommendedChoice), level: recommendedLevel(proposal) })}>{t("ask.useRecommended")}</button>
      <button type="button" className="button button-quiet" disabled={disabled} onClick={onSkip}>{t("ask.skip")}</button>
    </div>
  </section>;
}


/** Each section owns its comment thread; a revised graph is reviewed again before it runs. */
export function ImplementationPlanArtifact({ spec, pending = false, compact = false }: { spec: JsonRecord; pending?: boolean; compact?: boolean }) {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const comments = workspace.planComments[String(spec.id)] ?? {};
  const [editing, setEditing] = useState<string | null>(null);
  const nodes = (Array.isArray(spec.nodes) ? spec.nodes as JsonRecord[] : []).filter((node) => node.kind !== "start");
  const label = (node: JsonRecord) => String(node.label ?? t("studio.executionPlan")).replace(/\s*·\s*(?:start|crew|nexusgen|sandbox)\s*$/i, "");
  const assumptions = workspace.plan?.assumptions ?? [];
  const sections = [
    { id: "architecture", label: t("studio.architecture"), lines: nodes.map(label) },
    { id: "files", label: t("studio.targetFiles"), lines: [...new Set(nodes.flatMap((node) => [...(Array.isArray(node.expected_artifact_paths) ? node.expected_artifact_paths.map(String) : []), ...(Array.isArray(node.tasks) ? (node.tasks as JsonRecord[]).flatMap((task) => Array.isArray(task.expected_artifact_paths) ? task.expected_artifact_paths.map(String) : []) : [])]))] },
    { id: "roster", label: t("studio.roster"), lines: nodes.flatMap((node) => Array.isArray(node.agents) ? (node.agents as JsonRecord[]).map((agent) => `${String(agent.role)} · ${String(agent.model ?? "")} · ${String(node.label ?? "")}`) : node.kind === "sandbox" ? [`${String(node.label)} · ${t("studio.coder")} / ${t("studio.reviewer")}`] : []) },
    { id: "assumptions", label: t("ask.assumptions"), lines: pending ? assumptions : [] },
  ].filter((section) => section.lines.length > 0);
  const feedback = Object.entries(comments).filter(([, text]) => text.trim()).map(([section, text]) => ({ section, text: text.trim() }));
  const editableLine = (id: string, text: string) => <div className="ag-plan-line" key={id}>
    <button type="button" className="ag-plan-comment-target" aria-expanded={editing === id} onClick={() => setEditing(editing === id ? null : id)}><span>{text}</span><Icon name="chat" size={13} />{comments[id] && <span className="ag-count">1</span>}</button>
    {(editing === id || comments[id]) && <label className="ag-inline-comment"><span>{t("studio.inlineComment")}</span><textarea autoFocus={editing === id} rows={2} maxLength={1000} value={comments[id] ?? ""} onChange={(event) => workspace.commentOnPlan(String(spec.id), id, event.target.value)} placeholder={t("studio.commentPlaceholder")} /></label>}
  </div>;
  if (compact) return <div className="ag-execution-plan"><ol>{nodes.map((node, index) => <li key={String(node.id ?? index)}>{label(node)}</li>)}</ol>
    {sections.find((section) => section.id === "files") && <div className="ag-execution-files"><strong>{t("studio.targetFiles")}</strong><ul>{sections.find((section) => section.id === "files")?.lines.map((file) => <li key={file}>{file}</li>)}</ul></div>}
  </div>;
  return <section className="ag-artifact-card implementation-plan" aria-label={t("studio.implementationPlan")}>
    <header><Icon name="review" /><h3>{t("studio.implementationPlan")}</h3><span>{t(pending ? "studio.awaitingReview" : "studio.executionPlan")}</span></header>
    <h4>{String(spec.name ?? "")}</h4>
    {sections.map((section) => <details key={section.id} open={pending || section.id === "architecture"}><summary>{section.label}<span>{section.lines.length}</span></summary>
      {section.lines.map((line, index) => pending ? editableLine(`${section.label} / ${index + 1}`, line) : <div className="ag-plan-line" key={`${section.id}/${index}`}>{line}</div>)}
    </details>)}
    {pending && <div className="ask-actions"><button type="button" className="button button-primary" disabled={workspace.busy} onClick={() => void workspace.continuePlan(feedback)}>{t(feedback.length ? "studio.updatePlan" : "interface.proceed")}</button><small>{t(feedback.length ? "studio.revisedPlanReview" : "studio.planGate")}</small></div>}
    {!pending && feedback.length > 0 && <button type="button" className="button button-quiet" disabled={workspace.busy} onClick={() => { void workspace.startTask(`Plan feedback for the next team turn:\n${feedback.map((item) => `${item.section}: ${item.text}`).join("\n")}`, workspace.rigor); }}>{t("studio.sendFeedback")}</button>}
  </section>;
}
