// Interface language: the available locales, how a message key is resolved, and which locale a stored value means.
import { MESSAGES } from "./messages.mjs";

export const LOCALES = [{ id: "vi", label: "Tiếng Việt" }, { id: "en", label: "English" }];
export const DEFAULT_LOCALE = "vi";
export const LOCALE_STORAGE_KEY = "nexus_locale";

export const isLocale = (value) => LOCALES.some((locale) => locale.id === value);

export const resolveLocale = (value) => (isLocale(value) ? value : DEFAULT_LOCALE);

/** Fills `{name}` placeholders; a placeholder with no value is left visible rather than hidden. */
export function format(text, vars) {
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (whole, name) => (name in vars ? String(vars[name]) : whole));
}

/** A `t(key, vars)` function for one locale. A key missing from that locale falls back to English, then to the key itself. */
export function createTranslator(locale) {
  const table = MESSAGES[resolveLocale(locale)];
  return (key, vars) => format(table[key] ?? MESSAGES.en[key] ?? key, vars);
}

export function loadLocale(storage) {
  try { return resolveLocale(storage.getItem(LOCALE_STORAGE_KEY)); } catch { return DEFAULT_LOCALE; }
}

export function saveLocale(storage, locale) {
  try { storage.setItem(LOCALE_STORAGE_KEY, resolveLocale(locale)); } catch { /* storage can be blocked; the choice then lasts for this visit only */ }
}

/** Name of a run status in the current language; a status the tables do not know is shown as the server sent it. */
export function statusLabel(t, status) {
  const key = `status.${status}`;
  const text = t(key);
  return text === key ? status : text;
}

/** `Intl` locale tag for dates and numbers in the chosen interface language. */
export const dateLocale = (locale) => (resolveLocale(locale) === "vi" ? "vi-VN" : "en-GB");
