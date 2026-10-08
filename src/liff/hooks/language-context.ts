import { createContext } from "react";
import type th from "../locales/th.json";

export type Language = "th" | "en";
export type Translation = typeof th;

export type LanguageContextValue = {
  language: Language;
  setLanguage: (language: Language) => void;
  t: Translation;
};

export const LanguageContext = createContext<LanguageContextValue | null>(null);
