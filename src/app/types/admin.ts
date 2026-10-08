export type Admin = {
  id: number;
  username: string;
  last_login_at: string | null;
};

export type AdminLogin = {
  username: string;
  password: string;
};

export type District = {
  code: string;
  name_th: string;
  province_name_th: string;
};

export type VolunteerStatus = "pending" | "approved" | "rejected" | "suspended";

export type VolunteerAction = "approve" | "reject" | "suspend";

export type Volunteer = {
  id: number;
  full_name: string;
  phone: string;
  district_code: string;
  status: VolunteerStatus;
  approved_at: string | null;
  created_at: string;
};

export type VolunteerPage = {
  items: Volunteer[];
  total: number;
  limit: number;
  offset: number;
};

export type VolunteerFilters = {
  status: VolunteerStatus | null;
  districtCode: string | null;
  limit: number;
  offset: number;
};
