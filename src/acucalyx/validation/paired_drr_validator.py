"""
AcuCalyx Validation: Paired Physical C-Arm vs Synthetic DRR Validator (Phase 5 / M3)

Governing Requirement: Frozen Plan v5.1 (Section 4 & Section 6.3)
Implements Protocol M3.3:
1. Multi-metric Landmark Projection Error (LPE) on physical C-arm detector plane:
   - Evaluated across fiducial beads, calculus centroid, calyx apex, rib margins, and needle markers.
   - Comprehensive distribution statistics: Mean, SD, Median, IQR, 95th percentile, and Max error.
2. Radiometric image similarity across region of interest (ROI):
   - Structural Similarity Index (SSIM)
   - Normalized Cross-Correlation (NCC)
3. Formal Gate M3.3 compliance verification against clinical detector tolerances.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from scipy import stats
from skimage import metrics as ski_metrics


@dataclass(frozen=True)
class LandmarkObservation:
    """Paired 2D detector observation of a corresponding physical and synthetic landmark."""
    landmark_id: str
    anatomical_category: str  # 'fiducial', 'stone', 'calyx_apex', 'rib_margin', 'needle'
    physical_carm_coords_px: Tuple[float, float]
    drr_projected_coords_px: Tuple[float, float]

    def compute_error_px(self) -> float:
        """Euclidean distance on detector plane in pixels."""
        dx = self.physical_carm_coords_px[0] - self.drr_projected_coords_px[0]
        dy = self.physical_carm_coords_px[1] - self.drr_projected_coords_px[1]
        return math.sqrt(dx**2 + dy**2)

    def compute_error_mm(self, pixel_pitch_mm: Tuple[float, float]) -> float:
        """Euclidean distance on detector plane converted to physical millimeters."""
        dx_mm = (self.physical_carm_coords_px[0] - self.drr_projected_coords_px[0]) * pixel_pitch_mm[0]
        dy_mm = (self.physical_carm_coords_px[1] - self.drr_projected_coords_px[1]) * pixel_pitch_mm[1]
        return math.sqrt(dx_mm**2 + dy_mm**2)


@dataclass
class PairedFluoroscopyValidationReport:
    """Comprehensive Protocol M3.3 evaluation report for a paired C-arm exposure."""
    view_name: str
    gantry_primary_deg: float
    gantry_secondary_deg: float
    total_landmarks_evaluated: int
    mean_lpe_mm: float
    sd_lpe_mm: float
    median_lpe_mm: float
    iqr_lpe_mm: float
    p95_lpe_mm: float
    max_lpe_mm: float
    per_landmark_residuals_mm: Dict[str, float]
    ssim: Optional[float] = None
    ncc: Optional[float] = None
    is_gate_passed: bool = True
    gate_failure_reasons: List[str] = field(default_factory=list)


def compute_normalized_cross_correlation(img1: np.ndarray, img2: np.ndarray) -> float:
    """Computes Normalized Cross-Correlation (NCC) between two 2D grayscale images."""
    if img1.shape != img2.shape:
        raise ValueError(f"Image shapes must match for NCC: {img1.shape} vs {img2.shape}")
    a = img1.astype(np.float64) - np.mean(img1)
    b = img2.astype(np.float64) - np.mean(img2)
    denom = np.sqrt(np.sum(a**2) * np.sum(b**2))
    if denom < 1e-9:
        return 0.0
    return float(np.sum(a * b) / denom)


class PairedCarmDRRValidator:
    """
    Evaluates 2D geometric and radiometric concordance between physical fluoroscopy
    and AcuCalyx synthetic DRRs.
    """

    def __init__(
        self,
        max_median_lpe_mm: float = 1.8,
        max_p95_lpe_mm: float = 3.5,
        min_ssim: float = 0.75,
        min_ncc: float = 0.85
    ):
        self.max_median_lpe_mm = max_median_lpe_mm
        self.max_p95_lpe_mm = max_p95_lpe_mm
        self.min_ssim = min_ssim
        self.min_ncc = min_ncc

    def evaluate_paired_view(
        self,
        view_name: str,
        landmarks: List[LandmarkObservation],
        pixel_pitch_mm: Tuple[float, float],
        gantry_primary_deg: float = 0.0,
        gantry_secondary_deg: float = 0.0,
        physical_image_roi: Optional[np.ndarray] = None,
        drr_image_roi: Optional[np.ndarray] = None
    ) -> PairedFluoroscopyValidationReport:
        """
        Conducts full multi-metric Protocol M3.3 assessment for a paired fluoroscopy frame.
        """
        if not landmarks:
            raise ValueError("At least one landmark observation required for evaluation")

        errors_mm = [obs.compute_error_mm(pixel_pitch_mm) for obs in landmarks]
        residuals_map = {obs.landmark_id: round(err, 3) for obs, err in zip(landmarks, errors_mm)}

        mean_err = float(np.mean(errors_mm))
        sd_err = float(np.std(errors_mm))
        median_err = float(np.median(errors_mm))
        iqr_err = float(stats.iqr(errors_mm))
        p95_err = float(np.percentile(errors_mm, 95))
        max_err = float(np.max(errors_mm))

        failures = []
        if median_err > self.max_median_lpe_mm:
            failures.append(
                f"Median LPE ({median_err:.2f} mm) exceeds acceptance threshold ({self.max_median_lpe_mm:.2f} mm)"
            )
        if p95_err > self.max_p95_lpe_mm:
            failures.append(
                f"95th percentile LPE ({p95_err:.2f} mm) exceeds threshold ({self.max_p95_lpe_mm:.2f} mm)"
            )

        # Radiometric metrics if ROIs provided
        computed_ssim = None
        computed_ncc = None

        if physical_image_roi is not None and drr_image_roi is not None:
            computed_ncc = compute_normalized_cross_correlation(physical_image_roi, drr_image_roi)
            # SSIM requires uint8 or float within [0, 1]
            data_range = 255.0 if physical_image_roi.dtype == np.uint8 else 1.0
            computed_ssim = float(
                ski_metrics.structural_similarity(
                    physical_image_roi,
                    drr_image_roi,
                    data_range=data_range
                )
            )

            if computed_ncc < self.min_ncc:
                failures.append(
                    f"Normalized Cross-Correlation ({computed_ncc:.3f}) below threshold ({self.min_ncc:.3f})"
                )
            if computed_ssim < self.min_ssim:
                failures.append(
                    f"Structural Similarity Index ({computed_ssim:.3f}) below threshold ({self.min_ssim:.3f})"
                )

        is_passed = len(failures) == 0

        return PairedFluoroscopyValidationReport(
            view_name=view_name,
            gantry_primary_deg=gantry_primary_deg,
            gantry_secondary_deg=gantry_secondary_deg,
            total_landmarks_evaluated=len(landmarks),
            mean_lpe_mm=round(mean_err, 3),
            sd_lpe_mm=round(sd_err, 3),
            median_lpe_mm=round(median_err, 3),
            iqr_lpe_mm=round(iqr_err, 3),
            p95_lpe_mm=round(p95_err, 3),
            max_lpe_mm=round(max_err, 3),
            per_landmark_residuals_mm=residuals_map,
            ssim=round(computed_ssim, 3) if computed_ssim is not None else None,
            ncc=round(computed_ncc, 3) if computed_ncc is not None else None,
            is_gate_passed=is_passed,
            gate_failure_reasons=failures
        )
