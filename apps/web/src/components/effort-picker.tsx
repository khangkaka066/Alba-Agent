"use client";

import { useModels } from "@/components/model-context";
import { useLocale } from "@/components/locale-provider";
import { effortChoices, rememberRecent } from "@/lib/models.mjs";

/** Effort changes the concrete account variant sent through the existing gateway. */
export function EffortPicker({ disabled = false }: { disabled?: boolean }) {
  const { models, selected, loading, choose } = useModels();
  const { t } = useLocale();
  if (loading || !selected) return null;
  const choices = effortChoices(models, selected);
  const adjustable = choices.length > 1;
  return <label className="nx-effort-picker" title={adjustable ? t("model.effort") : t("model.effortUnavailable")}>
    <span>{t("model.effort")}</span>
    <select aria-label={t("model.effort")} value={choices.length ? selected : "default"} disabled={disabled || !adjustable} onChange={(event) => {
      const choice = choices.find((item) => item.id === event.currentTarget.value);
      if (choice) { choose(choice.id); rememberRecent(window.localStorage, choice.id); }
    }}>
      {choices.length ? choices.map((choice) => <option key={choice.id} value={choice.id}>{choice.label}</option>) : <option value="default">{t("model.effortDefault")}</option>}
    </select>
  </label>;
}
