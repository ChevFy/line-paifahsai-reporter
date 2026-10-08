import type { Language } from "./language-context";

export const LANGUAGE_STORAGE_KEY = "paifahsai.language";

function isLanguage(value: unknown): value is Language {
  return value === "th" || value === "en";
}

export function getInitialLanguage(): Language {
  try {
    const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (isLanguage(stored)) return stored;
  } catch {
    // storage unavailable (private mode, blocked site data)
  }
  return navigator.language?.toLowerCase().startsWith("en") ? "en" : "th";
}

export function saveLanguage(language: Language) {
  try {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  } catch {
    // ignore: language still switches for this session
  }
}
