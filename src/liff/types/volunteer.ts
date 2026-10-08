export type VolunteerStatus = "pending" | "approved" | "rejected" | "suspended";

export type VolunteerCreate = {
  full_name: string;
  phone: string;
  district_code: string;
};

export type Volunteer = {
  id: number;
  full_name: string;
  phone: string;
  district_code: string;
  status: VolunteerStatus;
  approved_at: string | null;
  created_at: string;
};

export type VolunteerRegistrationResponse = {
  volunteer: Volunteer;
  created: boolean;
  message: string;
};
