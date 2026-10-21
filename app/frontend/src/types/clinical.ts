/**
 * Clinical domain and workflow state types for AcuCalyx Workstation.
 */

export type CaseWorkflowState =
  | 'UPLOADED'
  | 'VALIDATING'
  | 'READY'
  | 'ANATOMY_REVIEW'
  | 'PLAN_GENERATED'
  | 'CLINICIAN_REVIEW'
  | 'FINALIZED'
  | 'REJECTED';

export type KidneyLaterality = 'left' | 'right';

export interface PatientDemographics {
  patient_id: string;
  age: number;
  sex: 'M' | 'F' | 'OTHER';
  clinical_indication: string;
  scheduled_procedure_date?: string;
  privacy_status: 'RESTRICTED_ATTENDING_ONLY' | 'DEPARTMENT_SHARED' | 'DEIDENTIFIED_RESEARCH';
}

export interface CaseSummary {
  case_id: string;
  state: CaseWorkflowState;
  created_at: string;
  updated_at: string;
  target_side: KidneyLaterality;
  is_stale: boolean;
  active_candidate_id?: string | null;
  stone_count: number;
  candidate_count: number;
  clinical_notice: string;
  owner_doctor_id: string;
  owner_doctor_name: string;
  patient_id: string;
  patient_age: number;
  patient_sex: 'M' | 'F' | 'OTHER';
  clinical_indication: string;
  privacy_status: string;
}

export interface QualityGateMetrics {
  is_acceptable: boolean;
  critical_errors: string[];
  warnings: string[];
  slice_count: number;
  mean_slice_thickness_mm: number;
  mean_inter_slice_spacing_mm: number;
  slice_spacing_std_mm: number;
  gantry_tilt_degrees: number;
  is_helical: boolean;
}
