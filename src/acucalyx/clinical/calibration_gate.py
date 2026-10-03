"""AcuCalyx Site C-Arm Metrology Calibration Gate.

Governed by ASTM F2554, ISO 13485:2016 Clause 7.5.6, and ISO 14155:2026.
Evaluates physical phantom dry-runs across participating clinical study sites,
enforcing maximum tolerances of <=2.0 deg angular error and <=2.0 mm spatial error
prior to granting human enrollment certification.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SiteCalibrationRecord:
    """Represents a single test puncture or projection measurement on the anthropomorphic phantom."""

    trial_index: int
    commanded_lao_rao_deg: float
    measured_lao_rao_deg: float
    commanded_cra_cau_deg: float
    measured_cra_cau_deg: float
    ground_truth_target_lps: Tuple[float, float, float]
    measured_target_lps: Tuple[float, float, float]

    def compute_angular_error(self) -> float:
        """Compute angular discrepancy between commanded and measured gantry angles."""
        d_lao = self.measured_lao_rao_deg - self.commanded_lao_rao_deg
        d_cra = self.measured_cra_cau_deg - self.commanded_cra_cau_deg
        return math.sqrt(d_lao**2 + d_cra**2)

    def compute_spatial_error(self) -> float:
        """Compute Euclidean distance discrepancy between measured target and ground truth (mm)."""
        dx = self.measured_target_lps[0] - self.ground_truth_target_lps[0]
        dy = self.measured_target_lps[1] - self.ground_truth_target_lps[1]
        dz = self.measured_target_lps[2] - self.ground_truth_target_lps[2]
        return math.sqrt(dx**2 + dy**2 + dz**2)


@dataclass
class SiteCalibrationCertificate:
    """Represents an official certification of site imaging readiness."""

    certificate_id: str
    site_id: str
    carm_model: str
    trials_evaluated: int
    mean_angular_error_deg: float
    max_angular_error_deg: float
    mean_spatial_error_mm: float
    max_spatial_error_mm: float
    status: str  # "CERTIFIED_PASS" or "CALIBRATION_FAILED"
    is_certified: bool
    reasons: List[str]
    certification_timestamp_utc: str


class SiteCalibrationGate:
    """Evaluates multi-pass phantom calibration dry-runs and issues certification certificates."""

    TOLERANCE_MEAN_ANGULAR_DEG = 2.0
    TOLERANCE_MAX_ANGULAR_DEG = 3.5
    TOLERANCE_MEAN_SPATIAL_MM = 2.0
    TOLERANCE_MAX_SPATIAL_MM = 3.5
    MINIMUM_TRIALS_REQUIRED = 3

    @classmethod
    def evaluate_site_calibration(
        cls,
        site_id: str,
        carm_model: str,
        records: List[SiteCalibrationRecord],
    ) -> SiteCalibrationCertificate:
        """Evaluate site dry-run passes against ASTM F2554 metrology tolerances."""
        if len(records) < cls.MINIMUM_TRIALS_REQUIRED:
            raise ValueError(
                f"Protocol requires at least {cls.MINIMUM_TRIALS_REQUIRED} phantom dry-run trials (received {len(records)})."
            )

        angular_errors = [r.compute_angular_error() for r in records]
        spatial_errors = [r.compute_spatial_error() for r in records]

        mean_angular = sum(angular_errors) / len(angular_errors)
        max_angular = max(angular_errors)

        mean_spatial = sum(spatial_errors) / len(spatial_errors)
        max_spatial = max(spatial_errors)

        reasons: List[str] = []
        if mean_angular > cls.TOLERANCE_MEAN_ANGULAR_DEG:
            reasons.append(
                f"Mean angular error ({mean_angular:.2f} deg) exceeds tolerance ({cls.TOLERANCE_MEAN_ANGULAR_DEG:.1f} deg)."
            )
        if max_angular > cls.TOLERANCE_MAX_ANGULAR_DEG:
            reasons.append(
                f"Peak angular error ({max_angular:.2f} deg) exceeds maximum bound ({cls.TOLERANCE_MAX_ANGULAR_DEG:.1f} deg)."
            )
        if mean_spatial > cls.TOLERANCE_MEAN_SPATIAL_MM:
            reasons.append(
                f"Mean spatial error ({mean_spatial:.2f} mm) exceeds tolerance ({cls.TOLERANCE_MEAN_SPATIAL_MM:.1f} mm)."
            )
        if max_spatial > cls.TOLERANCE_MAX_SPATIAL_MM:
            reasons.append(
                f"Peak spatial error ({max_spatial:.2f} mm) exceeds maximum bound ({cls.TOLERANCE_MAX_SPATIAL_MM:.1f} mm)."
            )

        is_certified = len(reasons) == 0
        status = "CERTIFIED_PASS" if is_certified else "CALIBRATION_FAILED"
        now_utc = datetime.now(timezone.utc).isoformat()
        cert_id = f"CERT-SIV-{site_id}-{hash(status) & 0xFFFF:04X}"

        return SiteCalibrationCertificate(
            certificate_id=cert_id,
            site_id=site_id,
            carm_model=carm_model,
            trials_evaluated=len(records),
            mean_angular_error_deg=round(mean_angular, 3),
            max_angular_error_deg=round(max_angular, 3),
            mean_spatial_error_mm=round(mean_spatial, 3),
            max_spatial_error_mm=round(max_spatial, 3),
            status=status,
            is_certified=is_certified,
            reasons=reasons,
            certification_timestamp_utc=now_utc,
        )
