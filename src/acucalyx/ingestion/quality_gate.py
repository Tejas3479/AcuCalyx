"""
AcuCalyx Ingestion: DICOM Quality Gate and Geometric Integrity Validation

Implements a fail-closed quality gate verifying:
- ImageOrientationPatient and ImagePositionPatient completeness
- Direction cosines unit length and mutual orthogonality
- Slice spacing consistency (checks for missing slices or variable table speed)
- Gantry tilt (rejects tilted acquisitions that produce non-orthogonal volumes)
- Slice thickness threshold (flags >1.25mm, rejects >2.5mm)
- Contrast status and reconstruction kernel metadata extraction
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Sequence
import numpy as np


@dataclass(frozen=True)
class QualityGateResult:
    """Detailed evaluation result from the imaging quality gate."""
    passed: bool
    rejection_reasons: List[str]
    warnings: List[str]
    geometry_score: float      # [0.0, 1.0]
    resolution_score: float    # [0.0, 1.0]
    overall_quality_tier: str  # 'HIGH', 'ACCEPTABLE', 'INSUFFICIENT'
    slice_thickness_mm: float
    pixel_spacing_mm: Tuple[float, float]
    slice_spacing_mm: float
    is_contrast_enhanced: Optional[bool]
    reconstruction_kernel: Optional[str]


def evaluate_dicom_series_geometry(
    image_positions: Sequence[Sequence[float]],
    image_orientations: Sequence[Sequence[float]],
    pixel_spacings: Sequence[Sequence[float]],
    slice_thicknesses: Sequence[float],
    gantry_tilts: Optional[Sequence[float]] = None,
    reconstruction_kernels: Optional[Sequence[str]] = None,
    contrast_agents: Optional[Sequence[str]] = None
) -> QualityGateResult:
    """
    Evaluates geometric consistency across an entire DICOM slice series.
    Fail-closed: Returns passed=False if any critical geometric condition is violated.
    """
    reasons: List[str] = []
    warnings: List[str] = []
    
    n_slices = len(image_positions)
    if n_slices < 10:
        return QualityGateResult(
            passed=False,
            rejection_reasons=[f"Insufficient slices for 3D reconstruction (found {n_slices}, required >= 10)"],
            warnings=[],
            geometry_score=0.0,
            resolution_score=0.0,
            overall_quality_tier='INSUFFICIENT',
            slice_thickness_mm=0.0,
            pixel_spacing_mm=(0.0, 0.0),
            slice_spacing_mm=0.0,
            is_contrast_enhanced=None,
            reconstruction_kernel=None
        )

    # 1. Orientation check: all slices must share the same orientation
    ref_iop = np.array(image_orientations[0], dtype=np.float64)
    x_dir = ref_iop[0:3]
    y_dir = ref_iop[3:6]
    
    # Check unit vectors
    if not (np.isclose(np.linalg.norm(x_dir), 1.0, atol=1e-3) and np.isclose(np.linalg.norm(y_dir), 1.0, atol=1e-3)):
        reasons.append("ImageOrientationPatient direction cosines are not unit vectors")
    if not np.isclose(np.dot(x_dir, y_dir), 0.0, atol=1e-3):
        reasons.append("ImageOrientationPatient row and column vectors are not orthogonal")

    normal_dir = np.cross(x_dir, y_dir)
    normal_dir = normal_dir / np.linalg.norm(normal_dir)

    # Check orientation consistency across slices
    for idx, iop in enumerate(image_orientations[1:], start=1):
        if not np.allclose(iop, ref_iop, atol=1e-3):
            reasons.append(f"Slice {idx} has different ImageOrientationPatient than slice 0")
            break

    # 2. Slice spacing and ordering: project positions along normal
    positions = np.array(image_positions, dtype=np.float64)
    projected = np.dot(positions, normal_dir)
    sorted_indices = np.argsort(projected)
    sorted_proj = projected[sorted_indices]

    deltas = np.diff(sorted_proj)
    if np.any(deltas <= 0.0):
        reasons.append("Duplicate or non-advancing slice positions detected")

    mean_spacing = float(np.mean(deltas)) if len(deltas) > 0 else 0.0
    spacing_std = float(np.std(deltas)) if len(deltas) > 0 else 0.0
    
    if spacing_std > 0.05:  # Tolerance: 0.05 mm variation
        reasons.append(f"Non-uniform slice spacing detected (mean={mean_spacing:.3f}mm, std={spacing_std:.3f}mm). Missing slices suspected.")

    # 3. Gantry tilt check
    if gantry_tilts is not None:
        for tilt in gantry_tilts:
            if abs(float(tilt)) > 0.5:
                reasons.append(f"Gantry tilt of {tilt}° detected. AcuCalyx requires non-tilted acquisitions.")
                break

    # 4. Slice thickness checks
    mean_thickness = float(np.mean(slice_thicknesses))
    if mean_thickness > 2.5:
        reasons.append(f"Slice thickness {mean_thickness:.2f}mm exceeds safe limit of 2.5mm")
    elif mean_thickness > 1.25:
        warnings.append(f"Slice thickness {mean_thickness:.2f}mm exceeds optimal limit of 1.25mm; stair-step artifacts may affect small calyces")

    ref_ps = pixel_spacings[0]
    px_r, px_c = float(ref_ps[0]), float(ref_ps[1])
    if px_r > 1.2 or px_c > 1.2:
        warnings.append(f"Pixel spacing ({px_r:.2f}x{px_c:.2f}mm) is relatively coarse")

    # Scores
    passed = len(reasons) == 0
    geom_score = 1.0 if passed else max(0.0, 1.0 - len(reasons) * 0.3)
    res_score = max(0.0, min(1.0, 1.25 / max(1.0, mean_thickness)))
    
    if not passed:
        quality_tier = 'INSUFFICIENT'
    elif len(warnings) == 0 and mean_thickness <= 1.25:
        quality_tier = 'HIGH'
    else:
        quality_tier = 'ACCEPTABLE'

    kernel = reconstruction_kernels[0] if reconstruction_kernels else None
    has_contrast = bool(contrast_agents and contrast_agents[0] and contrast_agents[0].strip())

    return QualityGateResult(
        passed=passed,
        rejection_reasons=reasons,
        warnings=warnings,
        geometry_score=float(geom_score),
        resolution_score=float(res_score),
        overall_quality_tier=quality_tier,
        slice_thickness_mm=mean_thickness,
        pixel_spacing_mm=(px_r, px_c),
        slice_spacing_mm=mean_spacing,
        is_contrast_enhanced=has_contrast,
        reconstruction_kernel=kernel
    )
