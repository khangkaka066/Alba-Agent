"use client";

import { useState } from "react";
import { useLocale } from "@/components/locale-provider";

export type PlanChoice = { label: string; description: string; recommended: boolean };
export type PlanQuestion = { id: string; text: string; options: PlanChoice[]; allow_other: boolean };
export type PlanLevel = "solo" | "team" | "studio";
export type PlanOption = { id: string; level: PlanLevel; summary: string; agents: number; speed: "fast" | "medium" | "slow"; tradeoffs: string; recommended: boolean; reason: string };
export type PlanProposal = { status: "ready" | "needs_input"; assumptions: string[]; questions: PlanQuestion[]; options: PlanOption[] };
export type ProposalAnswers = { decisions: Array<{ question: string; answer: string }>; level: PlanLevel | null };

const OTHER = "__other__";

export function recommendedChoice(question: PlanQuestion): string {
  return (question.options.find((option) => option.recommended) ?? question.options[0]).label;
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
