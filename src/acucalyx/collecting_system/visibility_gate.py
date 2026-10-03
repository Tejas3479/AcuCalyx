"""
AcuCalyx Collecting System: Visibility Gate and State Classifier

Implements Module 4 of AcuCalyx v2:
Strictly distinguishes whether the pelvicalyceal system (PCS) is:
- Directly Opacified (Contrast CT)
- Hydronephrotic / Fluid-Distended (NCCT with visible urine pooling)
- Partially Visible (Focal distension)
- Anatomically Estimated (Standard non-distended NCCT)
- Not Assessable (Artifact / noise)

Rule: Never pretend an invisible calyx is an exact 3D target.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple
import numpy as np
from scipy import ndimage

from acucalyx.geometry.coordinates import SpatialOrientation


class PCSVisibilityState(str, Enum):
    DIRECTLY_OPACIFIED = "DIRECTLY_OPACIFIED"
    HYDRONEPHROTIC_DISTENDED = "HYDRONEPHROTIC_DISTENDED"
    PARTIALLY_VISIBLE = "PARTIALLY_VISIBLE"
    ANATOMICALLY_ESTIMATED = "ANATOMICALLY_ESTIMATED"
    NOT_ASSESSABLE = "NOT_ASSESSABLE"


@dataclass(frozen=True)
class PCSVisibilityResult:
    """Evaluation result for collecting-system visibility."""
    state: PCSVisibilityState
    confidence_score: float             # [0.0, 1.0]
    fluid_cavity_volume_mm3: float      # Volume of fluid-attenuation region inside kidney
    mean_internal_hu: float
    allows_direct_puncture_lock: bool   # False for ESTIMATED on NCCT (requires clinician review)
    clinical_notice: str


def classify_collecting_system_visibility(
    ct_volume_hu: np.ndarray,
    kidney_mask: np.ndarray,
    spatial_orientation: SpatialOrientation,
    is_contrast_enhanced: bool = False
) -> PCSVisibilityResult:
    """
    Classifies pelvicalyceal system visibility to prevent overconfident target claims.
    
    Args:
        ct_volume_hu: 3D CT volume in Hounsfield Units
        kidney_mask: 3D binary mask of kidney parenchyma
        spatial_orientation: SpatialOrientation instance
        is_contrast_enhanced: Metadata flag indicating contrast presence
    """
    if not np.any(kidney_mask):
        return PCSVisibilityResult(
            state=PCSVisibilityState.NOT_ASSESSABLE,
            confidence_score=0.0,
            fluid_cavity_volume_mm3=0.0,
            mean_internal_hu=-1000.0,
            allows_direct_puncture_lock=False,
            clinical_notice="Kidney parenchyma mask not available; collecting system cannot be assessed."
        )

    spacing = spatial_orientation.spacing
    voxel_vol = float(spacing[0] * spacing[1] * spacing[2])
    
    # Internal kidney region (eroded by ~3mm from outer capsule to isolate renal sinus / collecting system)
    struct = ndimage.generate_binary_structure(3, 1)
    erode_voxels = max(1, int(round(3.0 / np.mean(spacing))))
    eroded_kidney = ndimage.binary_erosion(kidney_mask > 0, structure=struct, iterations=erode_voxels)
    
    if not np.any(eroded_kidney):
        eroded_kidney = kidney_mask > 0

    internal_hu = ct_volume_hu[eroded_kidney].astype(np.float64)
    mean_hu = float(np.mean(internal_hu))

    # Case 1: Contrast-enhanced CT with opacified PCS (> 150 HU in collecting system)
    if is_contrast_enhanced:
        high_contrast_voxels = np.sum(internal_hu > 150.0)
        high_contrast_vol = high_contrast_voxels * voxel_vol
        if high_contrast_vol > 500.0:  # > 0.5 mL opacified cavity
            return PCSVisibilityResult(
                state=PCSVisibilityState.DIRECTLY_OPACIFIED,
                confidence_score=0.95,
                fluid_cavity_volume_mm3=float(high_contrast_vol),
                mean_internal_hu=mean_hu,
                allows_direct_puncture_lock=True,
                clinical_notice="Collecting system is directly opacified via excretory contrast. High geometric target confidence."
            )

    # Case 2: NCCT with fluid distension (0 to 18 HU urine pooling)
    fluid_mask_internal = (ct_volume_hu >= 0.0) & (ct_volume_hu <= 18.0) & eroded_kidney
    labeled_fluid, n_fluid = ndimage.label(fluid_mask_internal, structure=struct)
    
    max_cavity_voxels = 0
    total_fluid_voxels = int(np.sum(fluid_mask_internal))
    
    if n_fluid > 0:
        counts = ndimage.sum(fluid_mask_internal, labeled_fluid, range(1, n_fluid + 1))
        max_cavity_voxels = int(np.max(counts))

    total_fluid_vol = total_fluid_voxels * voxel_vol
    max_cavity_vol = max_cavity_voxels * voxel_vol

    # Moderate/severe hydronephrosis: dominant fluid pocket > 1000 mm³ (~1 mL)
    if max_cavity_vol >= 1000.0:
        return PCSVisibilityResult(
            state=PCSVisibilityState.HYDRONEPHROTIC_DISTENDED,
            confidence_score=0.80,
            fluid_cavity_volume_mm3=float(total_fluid_vol),
            mean_internal_hu=mean_hu,
            allows_direct_puncture_lock=True,
            clinical_notice="Moderate hydronephrosis detected. Calyces directly delineated by urine fluid distension."
        )
    # Mild/focal distension: fluid pocket between 300 and 1000 mm³
    elif max_cavity_vol >= 300.0:
        return PCSVisibilityResult(
            state=PCSVisibilityState.PARTIALLY_VISIBLE,
            confidence_score=0.60,
            fluid_cavity_volume_mm3=float(total_fluid_vol),
            mean_internal_hu=mean_hu,
            allows_direct_puncture_lock=True,
            clinical_notice="Focal calyceal fluid distension detected. Selected calyces partially visible."
        )
    # Standard non-hydronephrotic NCCT: calyces collapsed, invisible
    else:
        return PCSVisibilityResult(
            state=PCSVisibilityState.ANATOMICALLY_ESTIMATED,
            confidence_score=0.35,
            fluid_cavity_volume_mm3=float(total_fluid_vol),
            mean_internal_hu=mean_hu,
            allows_direct_puncture_lock=False,
            clinical_notice="Standard non-hydronephrotic NCCT. Calyces are collapsed and not directly visible. Target locations are anatomically estimated from priors; intraoperative ultrasound/fluoroscopy confirmation required."
        )
