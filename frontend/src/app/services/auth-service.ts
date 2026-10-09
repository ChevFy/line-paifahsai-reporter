import type { Admin, AdminLogin } from "../types/admin";
import { readApiError } from "../utils/api-error";
import { request } from "./api-client";

export async function login(credentials: AdminLogin): Promise<Admin> {
  const response = await request("/admin/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(credentials),
  });

  if (!response.ok) {
    throw await readApiError(response, "เข้าสู่ระบบไม่สำเร็จ");
  }

  return (await response.json()) as Admin;
}

export async function logout(): Promise<void> {
  const response = await request("/admin/logout", { method: "POST" });
  if (!response.ok) {
    throw await readApiError(response, "ออกจากระบบไม่สำเร็จ");
  }
}

// Returns null when there is no valid session (401); other failures throw
export async function getCurrentAdmin(): Promise<Admin | null> {
  const response = await request("/admin/me");

  if (response.status === 401) return null;
  if (!response.ok) {
    throw await readApiError(response, "ตรวจสอบการเข้าสู่ระบบไม่สำเร็จ");
  }

  return (await response.json()) as Admin;
}
