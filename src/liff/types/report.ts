export type District = {
  code: string;
  name: string;
};

export type ReportCreate = {
  client_request_id: string;
  latitude: number;
  longitude: number;
  district_code: string;
  description: string;
};

export type ReportOutcome =
  | "NEW_INCIDENT"
  | "MERGED"
  | "MERGED_RECENTLY_CLOSED"
  | "DUPLICATE_REQUEST";

export type ReportResponse = {
  report_id: string;
  incident_id: string;
  outcome: ReportOutcome;
  message: string;
  emergency_phone: string;
};

export type ApiErrorResponse = {
  detail?: {
    message?: string;
  };
};
