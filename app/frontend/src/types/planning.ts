/**
 * Planning, Pareto optimization, and trajectory metrics.
 */

export interface MetricValue {
  value: number | null;
  unit: string;
  status: 'MEASURED' | 'DERIVED' | 'ESTIMATED' | 'UNCERTAIN' | 'NOT_EVALUABLE';
  confidence: 'HIGH' | 'MEDIUM' | 'LOW' | 'UNASSESSED';
  reason?: string | null;
}

export interface CandidateTrajectory {
  candidate_id: string;
  target_calyx_id: string;
  target_calyx_name: string;
  entry_point_lps: [number, number, number];
  target_point_lps: [number, number, number];
  tract_length_mm: MetricValue;
  min_effective_clearance_mm: MetricValue;
  reachable_stone_fraction: MetricValue;
  required_scope_deflection_deg: MetricValue;
  parenchyma_depth_mm: MetricValue;
  infundibular_pelvic_angle_deg: MetricValue;
  access_rib_classification: string;
  pleural_relation: string;
  diaphragm_relation: string;
  is_pareto_optimal: boolean;
  confidence_tier: 'HIGH' | 'MODERATE' | 'LOW';
  recommended_sheath_french: string;
  clinical_summary_note: string;
}

export interface CandidateComparisonMatrix {
  case_id: string;
  target_kidney_side: string;
  candidates: CandidateTrajectory[];
  active_candidate_id: string | null;
  clinical_disclaimer: string;
}
