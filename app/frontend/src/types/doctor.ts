/**
 * Doctor authentication, session, and RBAC types.
 */

export type ClinicalRole =
  | 'CHIEF_SURGEON'
  | 'ATTENDING_SURGEON'
  | 'FELLOW'
  | 'RESIDENT'
  | 'RADIOLOGIST'
  | 'CLINICAL_ADMIN';

export interface DoctorProfile {
  doctor_id: string;
  username: string;
  full_name: string;
  title: string;
  department: string;
  institution: string;
  npi: string;
  email: string;
  role: ClinicalRole;
  avatar_color: string;
  created_at?: string;
}

export interface AuthTokenResponse {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
  doctor: DoctorProfile;
}

export interface StoredSession {
  doctor: DoctorProfile;
  token: string;
  timestamp: number;
}
