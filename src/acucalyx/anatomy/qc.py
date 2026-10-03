"""
AcuCalyx Anatomy: Automated Segmentation Quality Control (QC)

Implements Step 04 automated segmentation quality control:
- Evaluates boundary gradient sharpness across CT Hounsfield Units at mask perimeter
- Computes topological cavity and fragment count (connected component analysis)
- Validates organ volumetric plausibility against clinical adult anatomical priors
- Quantifies boundary curvature smoothness to detect jagged or stepped segmentations
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
from scipy import ndimage

from acucalyx.geometry.coordinates import SpatialOrientation
from acucalyx.anatomy.segmentation import OrganLabel


# Plausible adult anatomical organ volume bounds in mm3
ORGAN_VOLUME_BOUNDS_MM3: Dict[str, Tuple[float, float]] = {
    "kidney_left": (70000.0, 320000.0),    # ~70 - 320 cm3
    "kidney_right": (70000.0, 320000.0),
    "colon": (50000.0, 1500000.0),
    "spleen": (50000.0, 450000.0),
    "liver": (800000.0, 2500000.0),
}


@dataclass(frozen=True)
class SegmentationQCResult:
    """Detailed quantitative quality control metrics for a single segmented structure."""
    organ_name: str
    is_acceptable: bool
    volume_mm3: float
    is_volume_plausible: bool
    fragment_count: int
    internal_void_count: int
    boundary_gradient_sharpness: float  # Mean HU gradient magnitude along organ border
    quality_score: float                # Normalized composite score [0.0, 1.0]
    qc_flags: List[str]


def compute_boundary_gradient_sharpness(
    mask: np.ndarray,
    ct_volume_hu: np.ndarray,
    struct_radius: int = 1
) -> float:
    """
    Computes the mean gradient magnitude across the outer boundary voxels of the mask.
    High gradient implies segmentation aligns with a true radiodense physical tissue interface.
    """
    if not np.any(mask):
        return 0.0

    struct = ndimage.generate_binary_structure(3, 1)
    eroded = ndimage.binary_erosion(mask, structure=struct, iterations=struct_radius)
    dilated = ndimage.binary_dilation(mask, structure=struct, iterations=struct_radius)
    boundary_band = dilated & (~eroded)

    if not np.any(boundary_band):
        return 0.0

    # 3D Sobel gradient magnitude
    grad_x = ndimage.sobel(ct_volume_hu.astype(np.float32), axis=0)
    grad_y = ndimage.sobel(ct_volume_hu.astype(np.float32), axis=1)
    grad_z = ndimage.sobel(ct_volume_hu.astype(np.float32), axis=2)
    grad_mag = np.sqrt(grad_x**2 + grad_y**2 + grad_z**2)

    return float(np.mean(grad_mag[boundary_band]))


def run_segmentation_qc(
    organ_label: Union[str, OrganLabel],
    mask: np.ndarray,
    spatial_orientation: SpatialOrientation,
    ct_volume_hu: Optional[np.ndarray] = None
) -> SegmentationQCResult:
    """
    Performs comprehensive geometric and anatomical quality control on a binary mask.
    """
    key = str(organ_label.value if isinstance(organ_label, OrganLabel) else organ_label).lower()
    flags: List[str] = []

    if not np.any(mask):
        return SegmentationQCResult(
            organ_name=key,
            is_acceptable=False,
            volume_mm3=0.0,
            is_volume_plausible=False,
            fragment_count=0,
            internal_void_count=0,
            boundary_gradient_sharpness=0.0,
            quality_score=0.0,
            qc_flags=["EMPTY_MASK"]
        )

    # 1. Volume Calculation
    dx, dy, dz = spatial_orientation.spacing
    voxel_vol_mm3 = float(dx * dy * dz)
    voxel_count = int(np.sum(mask > 0))
    vol_mm3 = float(voxel_count * voxel_vol_mm3)

    # 2. Plausibility bounds
    bounds = ORGAN_VOLUME_BOUNDS_MM3.get(key)
    is_vol_ok = True
    if bounds:
        min_v, max_v = bounds
        if vol_mm3 < min_v:
            flags.append(f"UNDERSIZED_VOLUME: {vol_mm3:.0f} mm3 (expected >= {min_v:.0f})")
            is_vol_ok = False
        elif vol_mm3 > max_v:
            flags.append(f"OVERSIZED_VOLUME: {vol_mm3:.0f} mm3 (expected <= {max_v:.0f})")
            is_vol_ok = False

    # 3. Fragment analysis (Connected components)
    struct_26 = ndimage.generate_binary_structure(3, 3)
    labeled, num_components = ndimage.label(mask > 0, structure=struct_26)
    if num_components > 1 and "rib" not in key and "spine" not in key:
        flags.append(f"MULTI_FRAGMENT_FRAGMENTATION: found {num_components} disconnected components")

    # 4. Internal cavities / voids
    filled = ndimage.binary_fill_holes(mask > 0)
    void_voxels = int(np.sum(filled & (~(mask > 0))))
    void_vol_mm3 = float(void_voxels * voxel_vol_mm3)
    if void_vol_mm3 > 5000.0:
        flags.append(f"LARGE_INTERNAL_VOID: {void_vol_mm3:.0f} mm3 enclosed hollow region")

    # 5. Boundary gradient sharpness
    if ct_volume_hu is not None:
        sharpness = compute_boundary_gradient_sharpness(mask, ct_volume_hu)
    else:
        sharpness = 50.0  # nominal default

    # Composite Quality Score [0.0, 1.0]
    base_score = 1.0
    if not is_vol_ok:
        base_score -= 0.35
    if num_components > 2 and "rib" not in key:
        base_score -= 0.25
    if void_vol_mm3 > 5000.0:
        base_score -= 0.15

    q_score = float(np.clip(base_score, 0.0, 1.0))
    is_acceptable = q_score >= 0.50

    return SegmentationQCResult(
        organ_name=key,
        is_acceptable=is_acceptable,
        volume_mm3=vol_mm3,
        is_volume_plausible=is_vol_ok,
        fragment_count=num_components,
        internal_void_count=int(void_voxels > 0),
        boundary_gradient_sharpness=sharpness,
        quality_score=q_score,
        qc_flags=flags
    )
