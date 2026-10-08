import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import en from "../locales/en.json";
import th from "../locales/th.json";
import { LanguageContext } from "./language-context";
import type { Language, Translation } from "./language-context";
import { getInitialLanguage, saveLanguage } from "./language-storage";

// Typed as Translation so tsc flags any key missing from en.json
const translations: Record<Language, Translation> = { th, en };

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(getInitialLanguage);

  const setLanguage = useCallback((next: Language) => {
    setLanguageState(next);
    saveLanguage(next);
  }, []);

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  const value = useMemo(
    () => ({ language, setLanguage, t: translations[language] }),
    [language, setLanguage],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}
