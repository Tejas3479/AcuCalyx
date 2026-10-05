"""
AcuCalyx Ultrasound: Cross-Modal Phantom & Human Clinical Validation Gate
Governed by Milestone M14C of ACU-M14-EXEC-PLAN-2026-V2.

Provides:
1. Acoustic Window Agreement (Cohen's kappa >= 0.80).
2. Stone Shadow Concordance (Mean IoU >= 0.75).
3. Calyx Visibility Prediction (Sensitivity >= 85%, Specificity >= 85%).
4. Rib Shadow Boundary FLE (<= 2.0 mm).
5. NAVI Model Calibration vs Physical Phantom SNR (Pearson r >= 0.85).
6. Comprehensive Validation Certificate Generation.
"""

from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional, Tuple
import numpy as np


@dataclass(frozen=True)
class CrossModalValidationReport:
    """Consolidated validation report against M14C acceptance benchmarks."""
    window_cohens_kappa: float
    window_passed: bool  # >= 0.80
    stone_shadow_mean_iou: float
    stone_shadow_passed: bool  # >= 0.75
    calyx_visibility_sensitivity: float
    calyx_visibility_specificity: float
    calyx_visibility_passed: bool  # >= 0.85 both
    rib_shadow_mean_fle_mm: float
    rib_shadow_passed: bool  # <= 2.0 mm
    navi_pearson_r: float
    navi_passed: bool  # >= 0.85
    overall_certified: bool
    summary: str


def compute_cohens_kappa(
    rater_a: List[str],
    rater_b: List[str],
    categories: Optional[List[str]] = None,
) -> float:
    """Computes Cohen's kappa coefficient between two raters."""
    if len(rater_a) != len(rater_b) or len(rater_a) == 0:
        return 0.0

    if categories is None:
        categories = sorted(list(set(rater_a + rater_b)))

    n = len(rater_a)
    cat_to_idx = {c: i for i, c in enumerate(categories)}
    k = len(categories)
    conf = np.zeros((k, k), dtype=int)

    for a, b in zip(rater_a, rater_b):
        conf[cat_to_idx[a], cat_to_idx[b]] += 1

    # Observed agreement
    p_o = np.trace(conf) / n

    # Expected agreement
    row_sums = np.sum(conf, axis=1) / n
    col_sums = np.sum(conf, axis=0) / n
    p_e = np.sum(row_sums * col_sums)

    if 1.0 - p_e < 1e-9:
        return 1.0

    kappa = (p_o - p_e) / (1.0 - p_e)
    return float(kappa)


def compute_stone_shadow_iou(
    simulated_shadow_mask: np.ndarray,
    ground_truth_shadow_mask: np.ndarray,
) -> float:
    """Computes Intersection-over-Union (IoU) of acoustic shadow cones."""
    sim = np.asarray(simulated_shadow_mask, dtype=bool)
    gt = np.asarray(ground_truth_shadow_mask, dtype=bool)

    intersection = np.logical_and(sim, gt).sum()
    union = np.logical_or(sim, gt).sum()

    if union == 0:
        return 1.0 if intersection == 0 else 0.0

    return float(intersection / union)


def compute_binary_diagnostic_metrics(
    predictions: List[bool],
    ground_truths: List[bool],
) -> Tuple[float, float, float]:
    """
    Computes sensitivity, specificity, and accuracy for binary visibility prediction.
    """
    tp = sum(1 for p, g in zip(predictions, ground_truths) if p and g)
    tn = sum(1 for p, g in zip(predictions, ground_truths) if not p and not g)
    fp = sum(1 for p, g in zip(predictions, ground_truths) if p and not g)
    fn = sum(1 for p, g in zip(predictions, ground_truths) if not p and g)

    sensitivity = (tp / (tp + fn)) if (tp + fn) > 0 else 1.0
    specificity = (tn / (tn + fp)) if (tn + fp) > 0 else 1.0
    accuracy = ((tp + tn) / len(predictions)) if len(predictions) > 0 else 1.0

    return float(sensitivity), float(specificity), float(accuracy)


def compute_pearson_correlation(x: List[float], y: List[float]) -> float:
    """Computes Pearson correlation coefficient r between two vectors."""
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    arr_x = np.asarray(x, dtype=float)
    arr_y = np.asarray(y, dtype=float)

    vx = np.var(arr_x)
    vy = np.var(arr_y)
    if vx < 1e-9 or vy < 1e-9:
        return 0.0

    r = np.corrcoef(arr_x, arr_y)[0, 1]
    return float(r)


def evaluate_m14c_clinical_gate(
    window_predictions: List[str],
    window_expert_ground_truth: List[str],
    shadow_ious: List[float],
    calyx_vis_predictions: List[bool],
    calyx_vis_ground_truth: List[bool],
    rib_boundary_fles_mm: List[float],
    predicted_navis: List[float],
    measured_phantom_snrs: List[float],
) -> CrossModalValidationReport:
    """
    Evaluates simulated ultrasound performance across all five M14C acceptance benchmarks.
    """
    # 1. Acoustic window agreement (Cohen's kappa >= 0.80)
    kappa = compute_cohens_kappa(window_predictions, window_expert_ground_truth)
    pass_window = kappa >= 0.80

    # 2. Stone shadow concordance (Mean IoU >= 0.75)
    mean_iou = float(np.mean(shadow_ious)) if len(shadow_ious) > 0 else 0.0
    pass_shadow = mean_iou >= 0.75

    # 3. Calyx visibility (Sensitivity >= 85%, Specificity >= 85%)
    sens, spec, acc = compute_binary_diagnostic_metrics(calyx_vis_predictions, calyx_vis_ground_truth)
    pass_calyx = (sens >= 0.85) and (spec >= 0.85)

    # 4. Rib shadow boundary FLE (Mean FLE <= 2.0 mm)
    mean_fle = float(np.mean(rib_boundary_fles_mm)) if len(rib_boundary_fles_mm) > 0 else 999.0
    pass_fle = mean_fle <= 2.0

    # 5. NAVI correlation vs measured SNR (Pearson r >= 0.85)
    r_val = compute_pearson_correlation(predicted_navis, measured_phantom_snrs)
    pass_navi = r_val >= 0.85

    overall = pass_window and pass_shadow and pass_calyx and pass_fle and pass_navi

    summary = (
        f"M14C Gate: {'PASS (ALL BENCHMARKS SATISFIED)' if overall else 'FAIL'}. "
        f"Kappa={kappa:.3f} (>=0.80: {pass_window}), "
        f"Shadow IoU={mean_iou:.3f} (>=0.75: {pass_shadow}), "
        f"Calyx Sens={sens:.1%}/Spec={spec:.1%} (>=85%: {pass_calyx}), "
        f"Rib FLE={mean_fle:.2f}mm (<=2.0mm: {pass_fle}), "
        f"NAVI r={r_val:.3f} (>=0.85: {pass_navi})."
    )

    return CrossModalValidationReport(
        window_cohens_kappa=kappa,
        window_passed=pass_window,
        stone_shadow_mean_iou=mean_iou,
        stone_shadow_passed=pass_shadow,
        calyx_visibility_sensitivity=sens,
        calyx_visibility_specificity=spec,
        calyx_visibility_passed=pass_calyx,
        rib_shadow_mean_fle_mm=mean_fle,
        rib_shadow_passed=pass_fle,
        navi_pearson_r=r_val,
        navi_passed=pass_navi,
        overall_certified=overall,
        summary=summary,
    )
