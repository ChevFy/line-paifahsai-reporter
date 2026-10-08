import { API_BASE_URL } from "../config/api";
import liff from "../../liff";
import { getApiError } from "../utils/api-error";
import { AppError } from "../utils/app-error";
import type { District, ReportCreate, ReportResponse } from "../types/report";

async function request(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch {
    throw new AppError("network");
  }
}

async function authenticatedRequest(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const token = liff.getIDToken();
  if (!token) {
    throw new AppError("notLoggedIn");
  }

  return request(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...init.headers,
    },
  });
}

export async function getDistricts(): Promise<District[]> {
  const response = await request(`${API_BASE_URL}/districts`);
  if (!response.ok) {
    throw await getApiError(response, "loadDistricts");
  }

  const districts = (await response.json()) as Array<{
    code: string;
    name?: string;
    name_th?: string;
  }>;

  return districts.map((district) => ({
    code: district.code,
    name: district.name ?? district.name_th ?? district.code,
  }));
}

export async function submitReport(payload: ReportCreate): Promise<ReportResponse> {
  const response = await authenticatedRequest("/reports", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await getApiError(response, "submit");
  }

  return (await response.json()) as ReportResponse;
}

export async function uploadReportImage(reportId: string, image: File): Promise<void> {
  const formData = new FormData();
  formData.append("image", image);
  const response = await authenticatedRequest(`/reports/${reportId}/image`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw await getApiError(response, "upload");
  }
}
