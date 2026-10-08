import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { setUnauthorizedHandler } from "../services/api-client";
import { getCurrentAdmin, login, logout } from "../services/auth-service";
import type { AdminLogin } from "../types/admin";
import { errorMessage } from "../utils/api-error";
import { AuthContext } from "./auth-context";
import type { AuthState } from "./auth-context";

async function checkSession(): Promise<AuthState> {
  try {
    const admin = await getCurrentAdmin();
    return admin ? { kind: "signed-in", admin } : { kind: "signed-out", sessionExpired: false };
  } catch (reason) {
    return { kind: "error", message: errorMessage(reason, "ตรวจสอบการเข้าสู่ระบบไม่สำเร็จ") };
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ kind: "checking" });

  useEffect(() => {
    let cancelled = false;
    void checkSession().then((next) => {
      if (!cancelled) setState(next);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setState((current) =>
        current.kind === "signed-in" ? { kind: "signed-out", sessionExpired: true } : current,
      );
    });
    return () => setUnauthorizedHandler(() => undefined);
  }, []);

  const signIn = useCallback(async (credentials: AdminLogin) => {
    const admin = await login(credentials);
    setState({ kind: "signed-in", admin });
  }, []);

  const signOut = useCallback(async () => {
    await logout();
    setState({ kind: "signed-out", sessionExpired: false });
  }, []);

  const retry = useCallback(async () => {
    setState({ kind: "checking" });
    setState(await checkSession());
  }, []);

  const value = useMemo(
    () => ({ state, signIn, signOut, retry }),
    [state, signIn, signOut, retry],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
