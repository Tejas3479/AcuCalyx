"""AcuCalyx Plan-Execution Fidelity & Trajectory Concordance Evaluator.

Governed by ISO 14155:2026 procedural process endpoints.
Evaluates the geometric fidelity of the executed PCNL needle access relative to
the preoperative AcuCalyx planned corridor, assessing 3D angular deviation,
target-zone containment (<=3.0 mm), entry deviation, and depth concordance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Tuple


@dataclass
class PlanFidelityResult:
    """Represents the multi-dimensional concordance between planned and executed trajectories."""

    case_id: str
    target_zone_contained: bool
    target_tip_error_mm: float
    angular_deviation_deg: float
    entry_deviation_mm: float
    depth_deviation_mm: float
    target_zone_radius_mm: float
    is_concordant: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "angular_deviation_deg": round(self.angular_deviation_deg, 2),
            "case_id": self.case_id,
            "depth_deviation_mm": round(self.depth_deviation_mm, 2),
            "entry_deviation_mm": round(self.entry_deviation_mm, 2),
            "is_concordant": self.is_concordant,
            "target_tip_error_mm": round(self.target_tip_error_mm, 2),
            "target_zone_contained": self.target_zone_contained,
            "target_zone_radius_mm": self.target_zone_radius_mm,
        }


class PlanFidelityEvaluator:
    """Calculates rigorous 3D spatial and angular deviations between planned and executed needle tracts."""

    CONCORDANCE_MAX_ANGULAR_DEG = 5.0
    CONCORDANCE_MAX_ENTRY_MM = 10.0
    DEFAULT_FORNICEAL_RADIUS_MM = 3.0

    @classmethod
    def evaluate_fidelity(
        cls,
        case_id: str,
        planned_entry_lps: Tuple[float, float, float],
        planned_target_lps: Tuple[float, float, float],
        actual_entry_lps: Tuple[float, float, float],
        actual_tip_lps: Tuple[float, float, float],
        forniceal_radius_mm: float = DEFAULT_FORNICEAL_RADIUS_MM,
    ) -> PlanFidelityResult:
        """Evaluate geometric concordance between planned and intraoperative trajectories."""
        # Compute planned vector and length
        v_plan = (
            planned_target_lps[0] - planned_entry_lps[0],
            planned_target_lps[1] - planned_entry_lps[1],
            planned_target_lps[2] - planned_entry_lps[2],
        )
        len_plan = math.sqrt(v_plan[0]**2 + v_plan[1]**2 + v_plan[2]**2)

        # Compute actual vector and length
        v_act = (
            actual_tip_lps[0] - actual_entry_lps[0],
            actual_tip_lps[1] - actual_entry_lps[1],
            actual_tip_lps[2] - actual_entry_lps[2],
        )
        len_act = math.sqrt(v_act[0]**2 + v_act[1]**2 + v_act[2]**2)

        # 1. 3D Angular Deviation
        dot = (v_plan[0] * v_act[0] + v_plan[1] * v_act[1] + v_plan[2] * v_act[2])
        denom = len_plan * len_act
        cos_theta = max(-1.0, min(1.0, dot / denom if denom > 0 else 1.0))
        angular_deg = math.degrees(math.acos(cos_theta))

        # 2. Skin Entry Deviation
        entry_err = math.sqrt(
            (actual_entry_lps[0] - planned_entry_lps[0])**2 +
            (actual_entry_lps[1] - planned_entry_lps[1])**2 +
            (actual_entry_lps[2] - planned_entry_lps[2])**2
        )

        # 3. Target Tip Spatial Error
        tip_err = math.sqrt(
            (actual_tip_lps[0] - planned_target_lps[0])**2 +
            (actual_tip_lps[1] - planned_target_lps[1])**2 +
            (actual_tip_lps[2] - planned_target_lps[2])**2
        )

        # 4. Target-Zone Containment
        contained = (tip_err <= forniceal_radius_mm)

        # 5. Depth Deviation
        depth_err = abs(len_act - len_plan)

        # Overall procedural concordance
        is_concordant = (
            contained and
            (angular_deg <= cls.CONCORDANCE_MAX_ANGULAR_DEG) and
            (entry_err <= cls.CONCORDANCE_MAX_ENTRY_MM)
        )

        return PlanFidelityResult(
            case_id=case_id,
            target_zone_contained=contained,
            target_tip_error_mm=tip_err,
            angular_deviation_deg=angular_deg,
            entry_deviation_mm=entry_err,
            depth_deviation_mm=depth_err,
            target_zone_radius_mm=forniceal_radius_mm,
            is_concordant=is_concordant,
        )
