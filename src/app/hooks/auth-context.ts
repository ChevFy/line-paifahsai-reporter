import { createContext } from "react";
import type { Admin, AdminLogin } from "../types/admin";

export type AuthState =
  | { kind: "checking" }
  | { kind: "signed-in"; admin: Admin }
  | { kind: "signed-out"; sessionExpired: boolean }
  | { kind: "error"; message: string };

export type AuthContextValue = {
  state: AuthState;
  signIn: (credentials: AdminLogin) => Promise<void>;
  signOut: () => Promise<void>;
  retry: () => Promise<void>;
};

export const AuthContext = createContext<AuthContextValue | null>(null);
