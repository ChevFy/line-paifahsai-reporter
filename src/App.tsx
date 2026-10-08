import { useEffect, useState } from "react";
import liff, { initLiff } from "./liff";
import ReportPage from "./liff/pages/ReportPage";
import { LanguageProvider } from "./liff/hooks/LanguageProvider";
import { useLanguage } from "./liff/hooks/useLanguage";
import { formatError, toDisplayError } from "./liff/utils/app-error";
import type { DisplayError } from "./liff/utils/app-error";

export default function App() {
  return (
    <LanguageProvider>
      <AppContent />
    </LanguageProvider>
  );
}

function AppContent() {
  const { t } = useLanguage();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<DisplayError | null>(null);

  useEffect(() => {
    initLiff()
      .then(() => {
        if (!liff.isLoggedIn()) {
          liff.login();
          return;
        }
        setReady(true);
      })
      .catch((reason: unknown) => {
        setError(toDisplayError(reason, "liffInit"));
      });
  }, []);

  if (error) return <main className="status-page"><p className="error-text">{formatError(error, t)}</p></main>;
  if (!ready) return <main className="status-page"><p>{t.app.loading}</p></main>;

  return <ReportPage />;
}
