import { useState } from "react";
import type { FormEvent } from "react";
import { Navigate, useLocation } from "react-router";
import { AlertCircle, Flame, LogIn } from "lucide-react";
import { useAuth } from "../hooks/useAuth";
import { errorMessage } from "../utils/api-error";

function redirectTarget(state: unknown): string {
  if (state && typeof state === "object" && "from" in state && typeof state.from === "string") {
    return state.from;
  }
  return "/volunteers";
}

export default function LoginPage() {
  const { state, signIn } = useAuth();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (state.kind === "signed-in") {
    return <Navigate to={redirectTarget(location.state)} replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmitting || !username.trim() || !password) return;

    setIsSubmitting(true);
    setError(null);
    try {
      await signIn({ username: username.trim(), password });
    } catch (reason) {
      setError(errorMessage(reason, "เข้าสู่ระบบไม่สำเร็จ"));
      setPassword("");
      setIsSubmitting(false);
    }
  }

  const sessionExpired = state.kind === "signed-out" && state.sessionExpired;

  return (
    <main className="login-page">
      <form className="login-card" onSubmit={handleSubmit}>
        <div className="login-brand">
          <div className="brand-icon" aria-hidden="true">
            <Flame size={20} />
          </div>
          <div>
            <h1>ปายฟ้าใส · แอดมิน</h1>
            <p>เข้าสู่ระบบเพื่อจัดการจิตอาสาและเหตุไฟป่า</p>
          </div>
        </div>

        {sessionExpired && (
          <p className="notice-box" role="status">
            เซสชันหมดอายุแล้ว กรุณาเข้าสู่ระบบอีกครั้ง
          </p>
        )}

        <fieldset disabled={isSubmitting}>
          <label>
            ชื่อผู้ใช้
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
            />
          </label>
          <label>
            รหัสผ่าน
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
        </fieldset>

        {error && (
          <div className="error-box" role="alert">
            <AlertCircle size={16} />
            <p>{error}</p>
          </div>
        )}

        <button className="primary-button login-submit" type="submit" disabled={isSubmitting}>
          <LogIn size={20} />
          {isSubmitting ? "กำลังเข้าสู่ระบบ..." : "เข้าสู่ระบบ"}
        </button>
      </form>
    </main>
  );
}
