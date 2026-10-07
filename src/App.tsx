import { useEffect, useState } from "react";
import liff, { initLiff } from "./liff";
import ReportPage from "./liff/pages/ReportPage";

export default function App() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
        setError(reason instanceof Error ? reason.message : "เปิด LIFF ไม่สำเร็จ");
      });
  }, []);

  if (error) return <main className="status-page"><p className="error-text">{error}</p></main>;
  if (!ready) return <main className="status-page"><p>กำลังเตรียมแบบฟอร์ม...</p></main>;

  return <ReportPage />;
}
