"""
AcuCalyx Endoscopy: Milestone M15-V Validation Gate
Governed by ACU-M15-EXEC-PLAN-2026-V2 (Milestones M15.0 & M15.7).

Replaces Pearson correlation (r ≥ 0.88) and ASTM F2554-22 overclaims with rigorous agreement metrics:
- Mean Absolute Error (MAE), RMSE, systematic bias, and Bland–Altman 95% Limits of Agreement for continuous morphometry
- Cohen's Kappa (κ) with 95% confidence interval and Sensitivity/Specificity for categorical reachability
- Two-way random effects Intraclass Correlation Coefficient ICC(2,1) across multi-observer clinical reviewers
- Zero unexplained critical failures benchmark on M15.0 physical transparent phantoms
"""

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

from acucalyx.endoscopy.instrument_registry import (
    M15_REFERENCE_PHANTOMS,
    PhysicalPhantomSpecification,
    WorkingChannelTool,
)
from acucalyx.endoscopy.reachability_engine import ReachabilityStatus


@dataclass
class MorphometryValidationResult:
    """Continuous statistical agreement metrics for a geometric anatomical parameter."""
    parameter_name: str
    sample_size: int
    mean_absolute_error: float
    root_mean_square_error: float
    systematic_bias: float
    bland_altman_lower_limit_95: float
    bland_altman_upper_limit_95: float
    mae_threshold: float
    passed: bool
    details: str


@dataclass
class ReachabilityClassificationMetrics:
    """Chance-corrected categorical agreement and confusion matrix metrics."""
    total_evaluations: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    sensitivity: float
    specificity: float
    positive_predictive_value: float
    negative_predictive_value: float
    accuracy: float
    cohens_kappa: float
    kappa_ci_lower_95: float
    kappa_ci_upper_95: float
    passed: bool


@dataclass
class InterRaterReliabilityResult:
    """Multi-observer annotation consistency assessment."""
    parameter_name: str
    num_cases: int
    num_raters: int
    icc_value: Optional[float]  # ICC(2,1), None if sample size insufficient
    icc_threshold: float
    agreement_interpretation: str
    passed: bool


@dataclass
class PhysicalPhantomConcordanceResult:
    """Bench-top mechanical concordance against physical transparent phantoms."""
    total_phantom_calyces: int
    concordant_evaluations: int
    critical_discrepancies: int
    concordance_rate_percent: float
    passed: bool
    phantom_results: Dict[str, bool]


@dataclass
class M15ValidationGateReport:
    """Comprehensive Milestone M15-V Nonclinical Preoperative Evidence Gate Report."""
    gate_identifier: str = "ACU-M15-V-GATE-2026"
    status: str = "NOT_EVALUABLE"  # "PASS_FOR_NONCLINICAL_RESEARCH", "FAIL_CRITERIA_UNMET", "NOT_EVALUABLE"
    ipa_validation: Optional[MorphometryValidationResult] = None
    iw_validation: Optional[MorphometryValidationResult] = None
    classification_metrics: Optional[ReachabilityClassificationMetrics] = None
    inter_rater_reliability: Optional[InterRaterReliabilityResult] = None
    phantom_concordance: Optional[PhysicalPhantomConcordanceResult] = None
    overall_gate_passed: bool = False
    validation_timestamp: str = ""
    summary_findings: str = ""


# -----------------------------------------------------------------------------
# Statistical Agreement Calculators
# -----------------------------------------------------------------------------

def compute_continuous_agreement(
    pred_vals: np.ndarray,
    ref_vals: np.ndarray,
    param_name: str,
    mae_threshold: float,
    unit_str: str = "",
) -> MorphometryValidationResult:
    """
    Computes MAE, RMSE, systematic bias, and Bland-Altman 95% limits of agreement.
    """
    p = np.asarray(pred_vals, dtype=float)
    r = np.asarray(ref_vals, dtype=float)
    n = len(p)
    if n == 0:
        return MorphometryValidationResult(
            parameter_name=param_name,
            sample_size=0,
            mean_absolute_error=0.0,
            root_mean_square_error=0.0,
            systematic_bias=0.0,
            bland_altman_lower_limit_95=0.0,
            bland_altman_upper_limit_95=0.0,
            mae_threshold=mae_threshold,
            passed=False,
            details="Empty sample array",
        )

    diffs = p - r
    mae = float(np.mean(np.abs(diffs)))
    rmse = float(np.sqrt(np.mean(diffs**2)))
    bias = float(np.mean(diffs))
    sd = float(np.std(diffs, ddof=1)) if n > 1 else 0.0

    ba_lower = bias - 1.96 * sd
    ba_upper = bias + 1.96 * sd

    passed = mae <= mae_threshold

    details = (
        f"{param_name}: MAE = {mae:.2f} {unit_str} (Threshold ≤ {mae_threshold:.2f} {unit_str}). "
        f"Bias = {bias:+.2f} {unit_str}, Bland-Altman 95% limits: [{ba_lower:.2f}, {ba_upper:.2f}] {unit_str}."
    )

    return MorphometryValidationResult(
        parameter_name=param_name,
        sample_size=n,
        mean_absolute_error=mae,
        root_mean_square_error=rmse,
        systematic_bias=bias,
        bland_altman_lower_limit_95=ba_lower,
        bland_altman_upper_limit_95=ba_upper,
        mae_threshold=mae_threshold,
        passed=passed,
        details=details,
    )


def compute_classification_agreement(
    pred_reachable: np.ndarray,
    ref_reachable: np.ndarray,
    kappa_threshold: float = 0.82,
) -> ReachabilityClassificationMetrics:
    """
    Computes Cohen's Kappa with 95% confidence interval, sensitivity, specificity, PPV, NPV.
    """
    p = np.asarray(pred_reachable, dtype=bool)
    r = np.asarray(ref_reachable, dtype=bool)
    n = len(p)

    tp = int(np.sum(p & r))
    tn = int(np.sum((~p) & (~r)))
    fp = int(np.sum(p & (~r)))
    fn = int(np.sum((~p) & r))

    sensitivity = tp / max(1, (tp + fn))
    specificity = tn / max(1, (tn + fp))
    ppv = tp / max(1, (tp + fp))
    npv = tn / max(1, (tn + fn))
    acc = (tp + tn) / max(1, n)

    # Cohen's Kappa
    po = acc
    p_yes = ((tp + fp) / n) * ((tp + fn) / n)
    p_no = ((tn + fn) / n) * ((tn + fp) / n)
    pe = p_yes + p_no

    if (1.0 - pe) > 1e-6:
        kappa = (po - pe) / (1.0 - pe)
        # Approximate standard error of kappa
        se_kappa = math.sqrt(max(0.0, (po * (1.0 - po)) / (n * ((1.0 - pe)**2) + 1e-6)))
        kappa_lower = max(-1.0, kappa - 1.96 * se_kappa)
        kappa_upper = min(1.0, kappa + 1.96 * se_kappa)
    else:
        kappa = 1.0 if po == 1.0 else 0.0
        kappa_lower = kappa
        kappa_upper = kappa

    passed = (kappa >= kappa_threshold) and (sensitivity >= 0.88) and (specificity >= 0.85)

    return ReachabilityClassificationMetrics(
        total_evaluations=n,
        true_positives=tp,
        false_positives=fp,
        true_negatives=tn,
        false_negatives=fn,
        sensitivity=sensitivity,
        specificity=specificity,
        positive_predictive_value=ppv,
        negative_predictive_value=npv,
        accuracy=acc,
        cohens_kappa=kappa,
        kappa_ci_lower_95=kappa_lower,
        kappa_ci_upper_95=kappa_upper,
        passed=passed,
    )


def compute_icc_2_1(
    ratings_matrix: np.ndarray,
    param_name: str = "IPA",
    icc_threshold: float = 0.80,
) -> InterRaterReliabilityResult:
    """
    Computes two-way random effects single rater ICC(2,1) for absolute agreement.
    ratings_matrix: [n_cases, k_raters]
    """
    n, k = ratings_matrix.shape
    if n < 3 or k < 2:
        return InterRaterReliabilityResult(
            parameter_name=param_name,
            num_cases=n,
            num_raters=k,
            icc_value=None,
            icc_threshold=icc_threshold,
            agreement_interpretation="INSUFFICIENT_SAMPLE_SIZE: Sample size or rater count too small for variance analysis",
            passed=False,
        )

    # Mean squares via two-way ANOVA
    mean_case = np.mean(ratings_matrix, axis=1)
    mean_rater = np.mean(ratings_matrix, axis=0)
    grand_mean = np.mean(ratings_matrix)

    ss_total = np.sum((ratings_matrix - grand_mean)**2)
    ss_rows = k * np.sum((mean_case - grand_mean)**2)      # Cases
    ss_cols = n * np.sum((mean_rater - grand_mean)**2)     # Raters
    ss_error = max(0.0, ss_total - ss_rows - ss_cols)

    df_rows = n - 1
    df_cols = k - 1
    df_error = df_rows * df_cols

    ms_rows = ss_rows / max(1, df_rows)
    ms_cols = ss_cols / max(1, df_cols)
    ms_error = ss_error / max(1, df_error)

    denom = ms_rows + (k - 1) * ms_error + (k * (ms_cols - ms_error) / n)
    if denom > 1e-6:
        icc = (ms_rows - ms_error) / denom
    else:
        icc = 1.0
    icc = min(1.0, max(-1.0, float(icc)))

    if icc >= 0.90:
        interp = "Almost Perfect Agreement"
    elif icc >= 0.80:
        interp = "Substantial Agreement"
    elif icc >= 0.60:
        interp = "Moderate Agreement"
    else:
        interp = "Poor to Fair Agreement"

    passed = icc >= icc_threshold

    return InterRaterReliabilityResult(
        parameter_name=param_name,
        num_cases=n,
        num_raters=k,
        icc_value=icc,
        icc_threshold=icc_threshold,
        agreement_interpretation=interp,
        passed=passed,
    )


# -----------------------------------------------------------------------------
# Milestone M15-V Comprehensive Gate Evaluator
# -----------------------------------------------------------------------------

def evaluate_m15_validation_gate(
    ipa_pred: Optional[np.ndarray] = None,
    ipa_ref: Optional[np.ndarray] = None,
    iw_pred: Optional[np.ndarray] = None,
    iw_ref: Optional[np.ndarray] = None,
    class_pred: Optional[np.ndarray] = None,
    class_ref: Optional[np.ndarray] = None,
    multi_expert_ratings: Optional[np.ndarray] = None,
    phantom_measurements: Optional[Dict[str, Dict[str, Any]]] = None,
    manifest_path: Optional[Union[str, Path]] = None,
) -> M15ValidationGateReport:
    """
    Executes the comprehensive Milestone M15-V Validation Gate evaluation against
    clinical benchmark thresholds and M15.0 physical phantoms.

    FAILS CLOSED: If real reference, prediction, or benchtop phantom data is not
    provided, returns status="NOT_EVALUABLE" and overall_gate_passed=False.
    Automated self-approval with synthetic defaults is strictly prohibited under
    nonclinical evidence verification protocols.
    """
    from datetime import datetime, timezone

    # 1. Ingest from locked manifest if provided
    if manifest_path is not None:
        m_path = Path(manifest_path)
        if not m_path.is_file():
            return M15ValidationGateReport(
                gate_identifier="ACU-M15-V-GATE-2026",
                status="NOT_EVALUABLE",
                overall_gate_passed=False,
                validation_timestamp=datetime.now(timezone.utc).isoformat(),
                summary_findings=f"Evaluation blocked: locked reference manifest file not found: {manifest_path}",
            )
        try:
            with open(m_path, "r", encoding="utf-8") as f:
                m_data = json.load(f)
            if ipa_pred is None and "ipa_pred" in m_data:
                ipa_pred = np.asarray(m_data["ipa_pred"], dtype=float)
            if ipa_ref is None and "ipa_ref" in m_data:
                ipa_ref = np.asarray(m_data["ipa_ref"], dtype=float)
            if iw_pred is None and "iw_pred" in m_data:
                iw_pred = np.asarray(m_data["iw_pred"], dtype=float)
            if iw_ref is None and "iw_ref" in m_data:
                iw_ref = np.asarray(m_data["iw_ref"], dtype=float)
            if class_pred is None and "class_pred" in m_data:
                class_pred = np.asarray(m_data["class_pred"], dtype=bool)
            if class_ref is None and "class_ref" in m_data:
                class_ref = np.asarray(m_data["class_ref"], dtype=bool)
            if multi_expert_ratings is None and "multi_expert_ratings" in m_data:
                multi_expert_ratings = np.asarray(m_data["multi_expert_ratings"], dtype=float)
            if phantom_measurements is None and "phantom_measurements" in m_data:
                phantom_measurements = m_data["phantom_measurements"]
        except Exception as err:
            return M15ValidationGateReport(
                gate_identifier="ACU-M15-V-GATE-2026",
                status="NOT_EVALUABLE",
                overall_gate_passed=False,
                validation_timestamp=datetime.now(timezone.utc).isoformat(),
                summary_findings=f"Evaluation blocked: manifest parsing failure ({err}).",
            )

    # 2. Fail closed if any required clinical arrays or phantom measurements are missing
    if (
        ipa_pred is None or ipa_ref is None or
        iw_pred is None or iw_ref is None or
        class_pred is None or class_ref is None or
        multi_expert_ratings is None or
        phantom_measurements is None
    ):
        return M15ValidationGateReport(
            gate_identifier="ACU-M15-V-GATE-2026",
            status="NOT_EVALUABLE",
            overall_gate_passed=False,
            validation_timestamp=datetime.now(timezone.utc).isoformat(),
            summary_findings=(
                "Evaluation blocked: missing real reference, prediction, or physical phantom measurements. "
                "Automated self-approval with synthetic defaults is prohibited under nonclinical evidence standards. "
                "Ensure versioned adjudicated ground truth and empirical benchtop phantom measurements are supplied."
            ),
        )

    # 3. Continuous Morphometry Agreement
    ipa_result = compute_continuous_agreement(ipa_pred, ipa_ref, "Infundibulopelvic Angle (IPA)", mae_threshold=5.0, unit_str="deg")
    iw_result = compute_continuous_agreement(iw_pred, iw_ref, "Infundibular Width (IW)", mae_threshold=0.6, unit_str="mm")

    # 4. Categorical Reachability Classification
    class_result = compute_classification_agreement(class_pred, class_ref, kappa_threshold=0.82)

    # 5. Inter-Rater Reliability
    icc_result = compute_icc_2_1(multi_expert_ratings, param_name="IPA Expert Consistency", icc_threshold=0.80)

    # 6. Physical Phantom Concordance (Evaluates measured vs ground truth tolerances with zero synthetic fallbacks)
    phantom_results: Dict[str, bool] = {}
    total_calyces = 0
    concordant = 0
    missing_calyces = 0

    for pid, phantom in M15_REFERENCE_PHANTOMS.items():
        phantom_calyces_count = 0
        phantom_concordant_count = 0
        p_meas = phantom_measurements.get(pid, {}) if phantom_measurements else {}

        for cid, calyx in phantom.calyces.items():
            total_calyces += 1
            phantom_calyces_count += 1
            is_truth_acc = calyx.is_flexible_accessible_unloaded

            # Empirical measurement must be present for this calyx; zero synthetic fallback
            if cid in p_meas:
                is_pred_acc = bool(p_meas[cid].get("is_accessible", False))
                if is_truth_acc == is_pred_acc:
                    concordant += 1
                    phantom_concordant_count += 1
            else:
                missing_calyces += 1

        # Phantom passes ONLY if ALL calyces in that phantom were empirically measured and concordant
        phantom_results[pid] = (
            phantom_calyces_count > 0 and
            phantom_concordant_count == phantom_calyces_count
        )

    phantom_concordance = PhysicalPhantomConcordanceResult(
        total_phantom_calyces=total_calyces,
        concordant_evaluations=concordant,
        critical_discrepancies=total_calyces - concordant,
        concordance_rate_percent=(concordant / max(1, total_calyces)) * 100.0,
        passed=(total_calyces - concordant == 0 and missing_calyces == 0 and all(phantom_results.values())),
        phantom_results=phantom_results,
    )

    all_passed = (
        ipa_result.passed and
        iw_result.passed and
        class_result.passed and
        icc_result.passed and
        phantom_concordance.passed
    )

    status_str = "PASS_FOR_NONCLINICAL_RESEARCH" if all_passed else "FAIL_CRITERIA_UNMET"
    icc_str = f"{icc_result.icc_value:.3f}" if icc_result.icc_value is not None else "N/A"
    summary = (
        f"Milestone M15-V Gate: {status_str}. "
        f"IPA MAE: {ipa_result.mean_absolute_error:.2f}° (Limit ≤ 5.0°); "
        f"IW MAE: {iw_result.mean_absolute_error:.2f} mm (Limit ≤ 0.6 mm); "
        f"Cohen's κ: {class_result.cohens_kappa:.3f} (Limit ≥ 0.82, Lower 95% CI: {class_result.kappa_ci_lower_95:.3f}); "
        f"ICC(2,1): {icc_str} (Limit ≥ 0.80); "
        f"Physical Phantom Concordance: {phantom_concordance.concordance_rate_percent:.1f}% ({phantom_concordance.critical_discrepancies} discrepancies, {missing_calyces} unmeasured)."
    )

    return M15ValidationGateReport(
        gate_identifier="ACU-M15-V-GATE-2026",
        status=status_str,
        ipa_validation=ipa_result,
        iw_validation=iw_result,
        classification_metrics=class_result,
        inter_rater_reliability=icc_result,
        phantom_concordance=phantom_concordance,
        overall_gate_passed=all_passed,
        validation_timestamp=datetime.now(timezone.utc).isoformat(),
        summary_findings=summary,
    )


def generate_synthetic_m15v_test_data() -> Dict[str, Any]:
    """
    Test Fixture Utility ONLY: Generates reproducible synthetic morphometry arrays
    and simulated bench measurements for unit testing statistical agreement calculators.
    NOT accessible or used by production validation routes.
    """
    np.random.seed(42)
    ipa_ref = np.array([
        72.0, 68.0, 74.0, 65.0, 52.0, 48.0, 50.0, 44.0, 28.0, 42.0,
        25.0, 32.0, 60.0, 55.0, 40.0, 35.0, 78.0, 82.0, 31.0, 46.0,
        58.0, 64.0, 49.0, 38.0, 70.0, 75.0, 29.0, 43.0, 53.0, 62.0
    ])
    noise = np.random.normal(0.0, 2.5, len(ipa_ref))
    ipa_pred = ipa_ref + noise

    np.random.seed(43)
    iw_ref = np.array([
        7.5, 6.8, 6.2, 5.8, 5.2, 4.8, 4.5, 4.2, 3.2, 4.0,
        3.8, 4.2, 5.5, 6.0, 4.8, 3.9, 8.0, 8.5, 3.4, 4.7,
        5.8, 6.5, 5.0, 4.1, 7.2, 7.8, 3.1, 4.4, 5.3, 6.4
    ])
    noise_iw = np.random.normal(0.0, 0.35, len(iw_ref))
    iw_pred = np.maximum(2.0, iw_ref + noise_iw)

    class_ref = (ipa_ref >= 35.0) & (iw_ref >= 4.0)
    class_pred = class_ref.copy()
    class_pred[8] = False

    np.random.seed(44)
    base = ipa_ref
    rater1 = base + np.random.normal(0.0, 2.0, len(base))
    rater2 = base + np.random.normal(0.2, 2.2, len(base))
    rater3 = base + np.random.normal(-0.1, 2.1, len(base))
    multi_expert_ratings = np.column_stack([rater1, rater2, rater3])

    # Empirical phantom measurements for all M15 reference phantoms
    phantom_measurements: Dict[str, Dict[str, Any]] = {}
    for pid, phantom in M15_REFERENCE_PHANTOMS.items():
        phantom_measurements[pid] = {}
        for cid, calyx in phantom.calyces.items():
            phantom_measurements[pid][cid] = {
                "is_accessible": calyx.is_flexible_accessible_unloaded,
                "measured_deflection_deg": 270.0,
            }

    return {
        "ipa_pred": ipa_pred,
        "ipa_ref": ipa_ref,
        "iw_pred": iw_pred,
        "iw_ref": iw_ref,
        "class_pred": class_pred,
        "class_ref": class_ref,
        "multi_expert_ratings": multi_expert_ratings,
        "phantom_measurements": phantom_measurements,
    }
