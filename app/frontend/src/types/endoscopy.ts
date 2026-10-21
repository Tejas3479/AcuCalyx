/**
 * M15 Endoscopic reachability, scope deflection, and caliber types.
 */

export interface InstrumentProfile {
  instrument_id: string;
  name: string;
  category: 'RIGID_NEPHROSCOPE' | 'FLEXIBLE_URETEROSCOPE' | 'MINI_PCNL' | 'DIGITAL_FLEXIBLE';
  outer_diameter_french: number;
  working_channel_french: number;
  max_deflection_deg: number;
  torque_tolerance_nm: number;
}

export interface CalyxReachabilityResult {
  calyx_name: string;
  calyx_id?: string;
  deflection_deg: number;
  is_reachable: boolean;
  strain: 'NONE' | 'LOW' | 'MODERATE' | 'HIGH';
  residual_distance_mm?: number;
}

export interface StoneCoverageReport {
  total_stones: number;
  reachable_stones: number;
  residual_fragment_risk_pct: number;
  recommended_extraction: 'BASKET' | 'HOLMIUM_LASER' | 'PNEUMATIC_LITHOTRIPTER';
}
