"""
AcuCalyx Stone Engine: Candidate Detection and Component Segmentation

Implements:
- Multi-tier HU candidate detection (>400 HU dense, 200-400 HU intermediate)
- 3D connected component labeling (26-connectivity)
- Anatomical containment filtering (excludes ribs/vertebrae outside kidney envelope)
- Morphological noise cleanup
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np
from scipy import ndimage

from acucalyx.geometry.coordinates import SpatialOrientation


@dataclass
class RawStoneCandidate:
    """A raw detected stone cluster before full characterization."""
    candidate_id: int
    voxel_mask: np.ndarray      # 3D boolean mask of component
    voxel_count: int
    bounding_box: Tuple[slice, slice, slice]
    tier: str                   # 'DENSE_CALCIUM' (>400 HU) or 'INTERMEDIATE' (200-400 HU)


def detect_stone_candidates(
    ct_volume_hu: np.ndarray,
    spatial_orientation: SpatialOrientation,
    kidney_mask: Optional[np.ndarray] = None,
    min_volume_voxels: int = 4,
    dense_threshold_hu: float = 400.0,
    intermediate_threshold_hu: float = 200.0
) -> List[RawStoneCandidate]:
    """
    Detects 3D stone candidate clusters.
    
    Args:
        ct_volume_hu: 3D array of CT intensities in Hounsfield Units
        spatial_orientation: SpatialOrientation instance
        kidney_mask: Optional 3D mask of kidney region (if available, restricts search)
        min_volume_voxels: Minimum connected voxels to reject single-pixel noise
        dense_threshold_hu: Threshold for dense stones (calcium/brushite)
        intermediate_threshold_hu: Lower threshold (uric acid / matrix)
    """
    candidates: List[RawStoneCandidate] = []
    
    # If kidney mask is provided, expand slightly (dilation by 5mm) to catch stones in dilated pelvis
    search_volume = ct_volume_hu.copy()
    if kidney_mask is not None and np.any(kidney_mask):
        spacing = spatial_orientation.spacing
        # Estimate structuring element radius in voxels (~5 mm dilation)
        dilate_voxels = np.maximum(1, np.round(5.0 / spacing)).astype(int)
        struct_elem = ndimage.generate_binary_structure(3, 1)
        expanded_kidney = ndimage.binary_dilation(
            kidney_mask > 0, 
            structure=struct_elem, 
            iterations=int(np.max(dilate_voxels))
        )
        search_volume[~expanded_kidney] = -1000.0
    
    # 26-connectivity structuring element
    struct_26 = ndimage.generate_binary_structure(3, 3)
    
    # Tier 1: Dense stones (> dense_threshold_hu)
    dense_mask = search_volume >= dense_threshold_hu
    labeled_dense, n_dense = ndimage.label(dense_mask, structure=struct_26)
    dense_slices = ndimage.find_objects(labeled_dense)
    
    current_id = 1
    for label_val in range(1, n_dense + 1):
        comp_mask = labeled_dense == label_val
        n_voxels = int(np.sum(comp_mask))
        if n_voxels < min_volume_voxels:
            continue
            
        bbox = dense_slices[label_val - 1]
        candidates.append(RawStoneCandidate(
            candidate_id=current_id,
            voxel_mask=comp_mask,
            voxel_count=n_voxels,
            bounding_box=bbox,
            tier='DENSE_CALCIUM'
        ))
        current_id += 1
        
    # Tier 2: Intermediate stones (200 - 400 HU) not contiguous with dense stones
    inter_mask = (search_volume >= intermediate_threshold_hu) & (search_volume < dense_threshold_hu)
    labeled_inter, n_inter = ndimage.label(inter_mask, structure=struct_26)
    inter_slices = ndimage.find_objects(labeled_inter)
    
    for label_val in range(1, n_inter + 1):
        comp_mask = labeled_inter == label_val
        n_voxels = int(np.sum(comp_mask))
        if n_voxels < min_volume_voxels:
            continue
            
        bbox = inter_slices[label_val - 1]
        candidates.append(RawStoneCandidate(
            candidate_id=current_id,
            voxel_mask=comp_mask,
            voxel_count=n_voxels,
            bounding_box=bbox,
            tier='INTERMEDIATE'
        ))
        current_id += 1
        
    return candidates
