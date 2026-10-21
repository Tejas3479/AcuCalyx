/**
 * Privacy-Preserving Federated Learning & Differential Privacy types.
 */

export interface PrivacyGuarantee {
  framework: string;
  hipaa_safe_harbor_verified: boolean;
  zero_phi_retention: boolean;
  current_epsilon_spent: number;
  target_epsilon_cap: number;
  budget_utilized_percentage: number;
  delta: number;
  l2_clip_threshold: number;
  noise_multiplier_sigma: number;
}

export interface PrivacyAuditLogEntry {
  audit_id: string;
  timestamp: string;
  doctor_id: string;
  doctor_name: string;
  cases_trained: number;
  l2_grad_norm_before_clip: number;
  l2_grad_norm_after_clip: number;
  noise_sigma: number;
  epsilon_spent: number;
  delta: number;
  status: string;
  privacy_proof_hash: string;
}

export interface FederatedRoundHistory {
  round_id: number;
  started_at: string;
  completed_at: string;
  participating_doctors: string[];
  cases_aggregated: number;
  mean_training_loss: number;
  consensus_accuracy: number;
  total_epsilon_spent: number;
}

export interface FederatedOverviewResponse {
  current_round: number;
  status: string;
  weights: Record<string, number>;
  bias: number;
  privacy_guarantee: PrivacyGuarantee;
  recent_audit_log: PrivacyAuditLogEntry[];
  rounds_history: FederatedRoundHistory[];
}
