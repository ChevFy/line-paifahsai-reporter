import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import liff, { initLiff } from "./liff";
import ReportPage from "./liff/pages/ReportPage";
import VolunteerRegisterPage from "./liff/pages/VolunteerRegisterPage";
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
          liff.login({ redirectUri: window.location.href });
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

  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<ReportPage />} />
      <Route path="/register" element={<VolunteerRegisterPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
