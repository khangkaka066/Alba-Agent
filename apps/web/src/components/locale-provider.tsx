"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { DEFAULT_LOCALE, createTranslator, loadLocale, saveLocale } from "@/lib/i18n.mjs";
import type { Locale, Translate } from "@/lib/i18n.mjs";

type LocaleValue = { locale: Locale; setLocale: (locale: Locale) => void; t: Translate };

const fallback: LocaleValue = { locale: DEFAULT_LOCALE, setLocale: () => undefined, t: createTranslator(DEFAULT_LOCALE) };
const LocaleContext = createContext<LocaleValue>(fallback);

/** Holds the interface language. The first paint uses the default so server and browser markup agree; the saved choice applies right after. */
export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(DEFAULT_LOCALE);
  useEffect(() => { setLocaleState(loadLocale(window.localStorage)); }, []);
  useEffect(() => { document.documentElement.lang = locale; }, [locale]);
  const setLocale = useCallback((next: Locale) => { setLocaleState(next); saveLocale(window.localStorage, next); }, []);
  const value = useMemo(() => ({ locale, setLocale, t: createTranslator(locale) }), [locale, setLocale]);
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export const useLocale = () => useContext(LocaleContext);
