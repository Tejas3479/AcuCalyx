"""
AcuCalyx Validation: Procedural Accuracy & Target Zone Evaluation Engine (Phase 5 / M3)

Governing Requirement: Frozen Plan v5.1 (Section 3, Section 5, & Section 7)
Implements:
1. Target Forniceal / Papillary Zone (Z_target) 3D anatomical representation.
2. Zone-based Target Localization Error (TLE_zone) vs Apex Centerline Error (TLE_apex).
3. ASTM F2554 four-vector error analysis:
   - Skin Entry Deviation (Delta_entry)
   - Trajectory Angular Deviation (Delta_theta)
   - Infundibular Coaxial Alignment Angle (theta_inf)
   - Depth Penetration / Over-Under Error (Delta_d)
4. 6-Tier Puncture Classification Taxonomy (from SUCCESS_FORNIX_AXIAL to FAILURE_COUNTER_PUNCTURE).
5. Exact one-sided 95% Clopper-Pearson binomial upper confidence limit calculation for safety events.
6. Multi-trial cohort statistics with metrology uncertainty integration.
"""

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from scipy import stats

from acucalyx.geometry.transforms import LineSegment3D
from acucalyx.phantom.phantom_spec import MetrologyUncertaintyBudget


class PunctureClassification(str, Enum):
    """6-tier clinical PCNL puncture classification taxonomy."""
    SUCCESS_FORNIX_AXIAL = "SUCCESS_FORNIX_AXIAL"           # Grade 1: Ideal papillary entry (theta_inf <= 15 deg)
    SUCCESS_FORNIX_OBLIQUE = "SUCCESS_FORNIX_OBLIQUE"       # Grade 2: Forniceal entry (theta_inf > 15 deg)
    SUBOPTIMAL_INFUNDIBULAR_NECK = "SUBOPTIMAL_INFUNDIBULAR_NECK" # Grade 3: Infundibular neck (arterial hazard)
    SUBOPTIMAL_PELVIC_DIRECT = "SUBOPTIMAL_PELVIC_DIRECT"   # Grade 4: Direct pelvic entry (hilar hazard)
    FAILURE_PARENCHYMAL_BYPASS = "FAILURE_PARENCHYMAL_BYPASS" # Grade 5: Missed calyx lumen into retroperitoneum
    FAILURE_COUNTER_PUNCTURE = "FAILURE_COUNTER_PUNCTURE"   # Grade 6: Through-and-through perforation of opposite wall


@dataclass(frozen=True)
class TargetFornicealZone:
    """
    3D Anatomical Target Zone representing the renal papilla / forniceal cup.
    A conical/cylindrical volume positioned at the forniceal apex and oriented
    along the infundibular axis.
    """
    calyx_name: str
    forniceal_apex_lps: np.ndarray        # [x, y, z] centerpoint of fornix in mm
    infundibular_axis_unit: np.ndarray    # Unit vector pointing into lumen/pelvis
    papilla_radius_mm: float = 3.0        # Typical radius (2.5 - 3.5 mm)
    papilla_depth_mm: float = 4.0         # Longitudinal depth of target zone

    def __post_init__(self):
        norm = np.linalg.norm(self.infundibular_axis_unit)
        if norm > 1e-6 and not np.isclose(norm, 1.0, atol=1e-4):
            object.__setattr__(self, "infundibular_axis_unit", self.infundibular_axis_unit / norm)

    def contains_point(self, point_lps: np.ndarray) -> bool:
        """
        Checks whether point_lps lies inside the 3D conical/cylindrical target papillary zone.
        """
        vec = point_lps - self.forniceal_apex_lps
        # Axial distance along infundibular direction
        axial_dist = float(np.dot(vec, self.infundibular_axis_unit))
        if axial_dist < -1.0 or axial_dist > self.papilla_depth_mm:
            return False

        # Radial distance orthogonal to infundibular axis
        radial_vec = vec - axial_dist * self.infundibular_axis_unit
        radial_dist = float(np.linalg.norm(radial_vec))

        # Radius allowed tapers slightly from apex to base or is cylindrical
        return radial_dist <= self.papilla_radius_mm

    def distance_to_zone(self, point_lps: np.ndarray) -> float:
        """
        Computes Zone-based Target Localization Error (TLE_zone).
        Returns 0.0 mm if point is inside Z_target; otherwise distance to closest boundary.
        """
        if self.contains_point(point_lps):
            return 0.0

        vec = point_lps - self.forniceal_apex_lps
        axial_dist = float(np.dot(vec, self.infundibular_axis_unit))
        radial_vec = vec - axial_dist * self.infundibular_axis_unit
        radial_dist = float(np.linalg.norm(radial_vec))

        # Clamped axial distance to zone segment [0, papilla_depth_mm]
        clamped_axial = max(0.0, min(axial_dist, self.papilla_depth_mm))
        d_axial = abs(axial_dist - clamped_axial)

        # Clamped radial distance to cylinder surface
        d_radial = max(0.0, radial_dist - self.papilla_radius_mm)

        return float(math.sqrt(d_axial**2 + d_radial**2))

    def distance_to_apex(self, point_lps: np.ndarray) -> float:
        """Computes Euclidean distance to ideal forniceal apex centerpoint (TLE_apex)."""
        return float(np.linalg.norm(point_lps - self.forniceal_apex_lps))


@dataclass
class PunctureExecutionTrial:
    """Raw physical data collected from a single puncture attempt."""
    trial_id: str
    operator_id: str
    planned_trajectory: LineSegment3D
    physical_needle_entry_lps: np.ndarray
    physical_needle_tip_lps: np.ndarray
    target_zone: TargetFornicealZone
    is_counter_puncture_observed: bool = False
    is_first_pass: bool = True
    fluoroscopy_time_seconds: float = 0.0
    dose_area_product_gy_cm2: float = 0.0
    repositioning_attempts: int = 0


@dataclass
class PunctureEvaluationResult:
    """Comprehensive ASTM F2554 evaluation metrics for a single puncture trial."""
    trial_id: str
    operator_id: str
    tle_zone_mm: float
    tle_apex_mm: float
    entry_deviation_mm: float
    angular_deviation_deg: float
    infundibular_alignment_angle_deg: float
    depth_error_mm: float
    puncture_classification: PunctureClassification
    is_clinically_acceptable: bool
    is_first_pass_success: bool
    is_counter_puncture: bool
    fluoroscopy_time_seconds: float
    dose_area_product_gy_cm2: float
    repositioning_attempts: int


def compute_exact_clopper_pearson_upper_bound(
    k_events: int,
    n_trials: int,
    confidence_level: float = 0.95
) -> float:
    """
    Computes exact one-sided Clopper-Pearson upper confidence limit for a binomial parameter.
    For k=0 events: p_upper = 1 - (1 - alpha)^(1/n)
    For k>0 events: Beta inverse CDF at confidence_level with (k+1, n-k) degrees of freedom.
    """
    if n_trials <= 0:
        return 1.0
    if k_events == 0:
        alpha = 1.0 - confidence_level
        return float(1.0 - (alpha ** (1.0 / n_trials)))
    if k_events >= n_trials:
        return 1.0

    return float(stats.beta.ppf(confidence_level, k_events + 1, n_trials - k_events))


class ProceduralAccuracyEvaluator:
    """
    Evaluates physical needle punctures against ASTM F2554 standards,
    anatomical acceptance criteria, and exact Clopper-Pearson safety limits.
    """

    def __init__(
        self,
        max_tle_zone_mm: float = 1.5,
        max_tle_apex_mm: float = 4.5,
        max_entry_dev_mm: float = 8.0,
        max_angular_dev_deg: float = 5.0,
        depth_error_bounds_mm: Tuple[float, float] = (-3.0, 4.5)
    ):
        self.max_tle_zone_mm = max_tle_zone_mm
        self.max_tle_apex_mm = max_tle_apex_mm
        self.max_entry_dev_mm = max_entry_dev_mm
        self.max_angular_dev_deg = max_angular_dev_deg
        self.depth_error_bounds_mm = depth_error_bounds_mm

    def evaluate_trial(self, trial: PunctureExecutionTrial) -> PunctureEvaluationResult:
        """Evaluates a single puncture trial across all 4 ASTM vectors and clinical taxonomy."""
        planned_traj = trial.planned_trajectory
        phys_entry = trial.physical_needle_entry_lps
        phys_tip = trial.physical_needle_tip_lps
        target_zone = trial.target_zone

        # 1. Target Localization Errors
        tle_zone = target_zone.distance_to_zone(phys_tip)
        tle_apex = target_zone.distance_to_apex(phys_tip)

        # 2. Skin Entry Deviation (Delta_entry)
        entry_dev = float(np.linalg.norm(phys_entry - planned_traj.start_point))

        # 3. Trajectory Angular Deviation (Delta_theta)
        phys_shaft = phys_tip - phys_entry
        phys_shaft_len = float(np.linalg.norm(phys_shaft))
        phys_dir = phys_shaft / max(phys_shaft_len, 1e-6)

        plan_dir = planned_traj.unit_direction
        cos_theta = float(np.clip(np.dot(phys_dir, plan_dir), -1.0, 1.0))
        angular_dev_deg = float(np.degrees(np.arccos(cos_theta)))

        # 4. Infundibular Coaxial Alignment Angle (theta_inf)
        cos_inf = float(np.clip(np.dot(phys_dir, target_zone.infundibular_axis_unit), -1.0, 1.0))
        theta_inf_deg = float(np.degrees(np.arccos(cos_inf)))

        # 5. Depth Penetration Error (Delta_d)
        phys_depth = phys_shaft_len
        plan_depth = planned_traj.length
        depth_error = phys_depth - plan_depth

        # 6. Puncture Classification
        if trial.is_counter_puncture_observed:
            classification = PunctureClassification.FAILURE_COUNTER_PUNCTURE
        elif target_zone.contains_point(phys_tip):
            if theta_inf_deg <= 15.0:
                classification = PunctureClassification.SUCCESS_FORNIX_AXIAL
            else:
                classification = PunctureClassification.SUCCESS_FORNIX_OBLIQUE
        elif tle_zone <= 3.0:
            classification = PunctureClassification.SUBOPTIMAL_INFUNDIBULAR_NECK
        elif tle_zone <= 10.0 and abs(depth_error) > 5.0:
            classification = PunctureClassification.SUBOPTIMAL_PELVIC_DIRECT
        else:
            classification = PunctureClassification.FAILURE_PARENCHYMAL_BYPASS

        # 7. Clinical Acceptance Decision
        is_acceptable = (
            (classification in [PunctureClassification.SUCCESS_FORNIX_AXIAL, PunctureClassification.SUCCESS_FORNIX_OBLIQUE])
            and (tle_zone <= self.max_tle_zone_mm)
            and (angular_dev_deg <= self.max_angular_dev_deg)
            and (self.depth_error_bounds_mm[0] <= depth_error <= self.depth_error_bounds_mm[1])
            and not trial.is_counter_puncture_observed
        )

        is_first_pass_success = is_acceptable and trial.is_first_pass and (trial.repositioning_attempts == 0)

        return PunctureEvaluationResult(
            trial_id=trial.trial_id,
            operator_id=trial.operator_id,
            tle_zone_mm=round(tle_zone, 3),
            tle_apex_mm=round(tle_apex, 3),
            entry_deviation_mm=round(entry_dev, 3),
            angular_deviation_deg=round(angular_dev_deg, 3),
            infundibular_alignment_angle_deg=round(theta_inf_deg, 3),
            depth_error_mm=round(depth_error, 3),
            puncture_classification=classification,
            is_clinically_acceptable=is_acceptable,
            is_first_pass_success=is_first_pass_success,
            is_counter_puncture=trial.is_counter_puncture_observed,
            fluoroscopy_time_seconds=trial.fluoroscopy_time_seconds,
            dose_area_product_gy_cm2=trial.dose_area_product_gy_cm2,
            repositioning_attempts=trial.repositioning_attempts
        )

    def evaluate_cohort(
        self,
        trials: List[PunctureExecutionTrial],
        metrology_budget: Optional[MetrologyUncertaintyBudget] = None
    ) -> Dict[str, Any]:
        """
        Evaluates a complete experimental cohort of puncture trials.
        Calculates descriptive statistics, first-pass rates, exact Clopper-Pearson safety limits,
        and metrology uncertainty adjustment.
        """
        if not trials:
            return {"error": "Empty trial cohort"}

        results = [self.evaluate_trial(t) for t in trials]
        n = len(results)

        tle_zones = [r.tle_zone_mm for r in results]
        tle_apexes = [r.tle_apex_mm for r in results]
        entry_devs = [r.entry_deviation_mm for r in results]
        ang_devs = [r.angular_deviation_deg for r in results]
        depth_errs = [r.depth_error_mm for r in results]
        fluoro_times = [r.fluoroscopy_time_seconds for r in results]
        daps = [r.dose_area_product_gy_cm2 for r in results]

        # Safety binary events
        counter_puncture_count = sum(1 for r in results if r.is_counter_puncture)
        acceptable_count = sum(1 for r in results if r.is_clinically_acceptable)
        first_pass_count = sum(1 for r in results if r.is_first_pass_success)

        # Exact one-sided 95% Clopper-Pearson upper risk limits
        cp_upper_counter = compute_exact_clopper_pearson_upper_bound(counter_puncture_count, n, 0.95)

        # Metrology uncertainty
        budget_report = metrology_budget.generate_uncertainty_report() if metrology_budget else None

        return {
            "sample_size_n": n,
            "clinical_success_rate_pct": round(acceptable_count / n * 100.0, 1),
            "first_pass_success_rate_pct": round(first_pass_count / n * 100.0, 1),
            "counter_puncture_count": counter_puncture_count,
            "counter_puncture_clopper_pearson_95_upper_pct": round(cp_upper_counter * 100.0, 2),
            "safety_claim": (
                f"{counter_puncture_count} observed counter-punctures in {n} trials yields "
                f"an exact one-sided 95% Clopper-Pearson upper risk limit of {cp_upper_counter * 100.0:.2f}%."
            ),
            "tle_zone_stats": {
                "mean_mm": round(float(np.mean(tle_zones)), 3),
                "sd_mm": round(float(np.std(tle_zones)), 3),
                "median_mm": round(float(np.median(tle_zones)), 3),
                "iqr_mm": round(float(stats.iqr(tle_zones)), 3),
                "p95_mm": round(float(np.percentile(tle_zones, 95)), 3)
            },
            "tle_apex_stats": {
                "mean_mm": round(float(np.mean(tle_apexes)), 3),
                "median_mm": round(float(np.median(tle_apexes)), 3),
                "p95_mm": round(float(np.percentile(tle_apexes, 95)), 3)
            },
            "entry_deviation_stats": {
                "mean_mm": round(float(np.mean(entry_devs)), 3),
                "median_mm": round(float(np.median(entry_devs)), 3)
            },
            "angular_deviation_stats": {
                "mean_deg": round(float(np.mean(ang_devs)), 3),
                "median_deg": round(float(np.median(ang_devs)), 3)
            },
            "depth_error_stats": {
                "mean_mm": round(float(np.mean(depth_errs)), 3),
                "median_mm": round(float(np.median(depth_errs)), 3)
            },
            "fluoroscopy_stats": {
                "mean_time_s": round(float(np.mean(fluoro_times)), 1),
                "mean_dap_gy_cm2": round(float(np.mean(daps)), 3)
            },
            "metrology_uncertainty_budget": budget_report
        }
