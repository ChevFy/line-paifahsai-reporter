import { useEffect, useState } from "react";
import liff, { initLiff } from "./liff";

type Profile = { displayName: string; pictureUrl?: string; userId: string };

export default function App() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    initLiff()
      .then(async () => {
        // เปิดจากเบราว์เซอร์นอก LINE จะยังไม่ล็อกอิน
        if (!liff.isLoggedIn()) {
          liff.login();
          return;
        }
        setProfile(await liff.getProfile());
      })
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <p>เกิดข้อผิดพลาด: {error}</p>;
  if (!profile) return <p>กำลังโหลด...</p>;

  return (
    <div style={{ padding: 24, textAlign: "center" }}>
      <img src={profile.pictureUrl} width={96} style={{ borderRadius: "50%" }} />
      <h2>สวัสดี {profile.displayName}</h2>
      <p>เปิดใน LINE: {liff.isInClient() ? "ใช่" : "ไม่ใช่"}</p>
      <button onClick={() => liff.closeWindow()}>ปิดหน้าต่าง</button>
    </div>
  );
}