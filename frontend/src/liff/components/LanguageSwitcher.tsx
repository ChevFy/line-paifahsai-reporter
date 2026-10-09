import { Languages } from "lucide-react";
import { useLanguage } from "../hooks/useLanguage";

export default function LanguageSwitcher() {
  const { language, setLanguage, t } = useLanguage();
  const nextLanguage = language === "th" ? "en" : "th";

  return (
    <button
      className="language-switcher"
      type="button"
      onClick={() => setLanguage(nextLanguage)}
      aria-label={t.language.switchTo}
      title={t.language.switchTo}
    >
      <Languages size={16} />
      <span>{language === "th" ? t.language.english : t.language.thai}</span>
    </button>
  );
}
