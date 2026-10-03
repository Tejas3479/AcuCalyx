"""
AcuCalyx Anatomy: Multi-Organ Segmentation & Thoracic Access Model

Implements Step 03 of AcuCalyx v2.1:
- Manages multi-organ binary volumetric masks across the surgical access corridor:
  * Kidney parenchyma (Left, Right)
  * Ribs (10th, 11th, 12th individually indexed)
  * Spine (T11-L4 vertebrae)
  * Gastrointestinal (Colon, Small Bowel)
  * Visceral (Liver, Spleen)
  * Thoracic (Lung lower lobes, Pleural space reflection envelope)
- Distinct Thoracic Access Model:
  * Differentiates lung parenchyma from the pleural space reflection envelope
  * Models the intercostal neurovascular bundle risk zone along inferior rib margins
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union
import numpy as np
from scipy import ndimage

from acucalyx.geometry.coordinates import SpatialOrientation


class OrganLabel(str, Enum):
    KIDNEY_LEFT = "kidney_left"
    KIDNEY_RIGHT = "kidney_right"
    RIB_LEFT_10 = "rib_left_10"
    RIB_LEFT_11 = "rib_left_11"
    RIB_LEFT_12 = "rib_left_12"
    RIB_RIGHT_10 = "rib_right_10"
    RIB_RIGHT_11 = "rib_right_11"
    RIB_RIGHT_12 = "rib_right_12"
    VERTEBRAE_SPINE = "vertebrae_spine"
    COLON = "colon"
    SMALL_BOWEL = "small_bowel"
    LIVER = "liver"
    SPLEEN = "spleen"
    LUNG_LEFT = "lung_lower_lobe_left"
    LUNG_RIGHT = "lung_lower_lobe_right"
    PLEURAL_ENVELOPE_LEFT = "pleural_envelope_left"
    PLEURAL_ENVELOPE_RIGHT = "pleural_envelope_right"
    INTERCOSTAL_NV_BUNDLE_LEFT = "intercostal_nv_bundle_left"
    INTERCOSTAL_NV_BUNDLE_RIGHT = "intercostal_nv_bundle_right"


@dataclass(frozen=True)
class StructureProvenance:
    """Explicit provenance and evidence-qualification payload for an anatomical structure."""
    organ_label: str
    tier: str                      # 'TIER1_BROAD_HAZARD', 'TIER2_PCNL_RENAL', 'REFERENCE_MANUAL', 'SYNTHETIC_FALLBACK'
    source_backend: str            # e.g., 'TotalSegmentator_v2', 'PCNL_Specialized_v1', 'Manual_Reference'
    model_version: str             # e.g., '2.2.0', '1.0.0'
    model_hash_sha256: str         # Cryptographic hash or 'N/A'
    training_dataset_id: str       # e.g., 'TotalSegmentator_Dataset_v2', 'PCNL_Internal_Cohort_v1'
    visibility_state: str          # 'DIRECTLY_VISUALIZED', 'PARTIAL', 'ESTIMATED_PRIOR', 'UNAVAILABLE'
    segmentation_status: str       # 'AUTOMATED_NEURAL', 'HEURISTIC_FALLBACK', 'CLINICIAN_EDITED'
    confidence_qc_score: float     # 0.0 to 1.0
    clinician_review_status: str = "PENDING"  # 'PENDING', 'ACCEPTED', 'OVERRIDDEN'


@dataclass
class AnatomicalCorridorMasks:
    """Container holding multi-organ binary masks and thoracic risk zones."""
    masks: Dict[str, np.ndarray] = field(default_factory=dict)
    spatial_orientation: Optional[SpatialOrientation] = None
    provenance: Dict[str, StructureProvenance] = field(default_factory=dict)

    def get_mask(self, label: Union[str, OrganLabel]) -> Optional[np.ndarray]:
        """Retrieves binary boolean mask for an organ, or None if not present."""
        key = str(label.value if isinstance(label, OrganLabel) else label)
        return self.masks.get(key)

    def set_mask(
        self,
        label: Union[str, OrganLabel],
        mask: np.ndarray,
        provenance: Optional[StructureProvenance] = None
    ) -> None:
        """Sets binary mask for an organ label with optional provenance."""
        key = str(label.value if isinstance(label, OrganLabel) else label)
        self.masks[key] = (mask > 0).astype(bool)
        if provenance is not None:
            self.provenance[key] = provenance

    @property
    def is_clinical_ready(self) -> bool:
        """Evaluates whether all segmented masks meet clinical-grade provenance requirements."""
        if not self.masks:
            return False
        if not self.provenance:
            return False
        for p in self.provenance.values():
            if p.segmentation_status == "HEURISTIC_FALLBACK":
                return False
        return True

    def get_kidney_mask(self, side: str = "left") -> Optional[np.ndarray]:
        """Convenience method returning kidney mask for specified side."""
        lbl = OrganLabel.KIDNEY_LEFT if side.lower() == "left" else OrganLabel.KIDNEY_RIGHT
        return self.get_mask(lbl)

    def get_combined_ribs_mask(self, side: str = "left") -> np.ndarray:
        """Merges 10th, 11th, and 12th rib masks into a single obstacle mask."""
        target_ribs = [
            OrganLabel.RIB_LEFT_10, OrganLabel.RIB_LEFT_11, OrganLabel.RIB_LEFT_12
        ] if side.lower() == "left" else [
            OrganLabel.RIB_RIGHT_10, OrganLabel.RIB_RIGHT_11, OrganLabel.RIB_RIGHT_12
        ]
        
        combined = None
        for r in target_ribs:
            m = self.get_mask(r)
            if m is not None:
                combined = m if combined is None else (combined | m)
                
        if combined is None:
            # Fallback to empty mask of same shape if any mask exists
            for m in self.masks.values():
                return np.zeros_like(m, dtype=bool)
            return np.zeros((1, 1, 1), dtype=bool)
        return combined


def derive_pleural_reflection_envelope(
    lung_mask: np.ndarray,
    spatial_orientation: SpatialOrientation,
    inferior_expansion_mm: float = 15.0
) -> np.ndarray:
    """
    Derives the pleural space / costodiaphragmatic recess reflection envelope.
    The pleural cavity extends ~15-20 mm inferior to the lung lower lobe parenchyma
    along the posterior chest wall (crossing the 12th rib level on expiration).
    """
    if not np.any(lung_mask):
        return np.zeros_like(lung_mask, dtype=bool)

    spacing = spatial_orientation.spacing  # [row_sp, col_sp, slice_sp]
    dz = spacing[2]
    # Number of slices to expand inferiorly (-Z direction)
    inferior_slices = max(1, int(round(inferior_expansion_mm / dz)))

    envelope = lung_mask.copy()
    # Dilate along inferior slices (-Z) to represent costodiaphragmatic pleural reflection
    for k in range(lung_mask.shape[2]):
        if np.any(lung_mask[:, :, k]):
            k_min = max(0, k - inferior_slices)
            envelope[:, :, k_min:k] |= lung_mask[:, :, k, np.newaxis]

    return envelope


def derive_intercostal_neurovascular_risk_zone(
    rib_mask: np.ndarray,
    spatial_orientation: SpatialOrientation,
    inferior_buffer_mm: float = 4.0
) -> np.ndarray:
    """
    Derives the intercostal neurovascular bundle risk zone.
    The intercostal vein, artery, and nerve run immediately along the
    INFERIOR border of each rib (subcostal groove). Puncturing along the
    superior border of a rib avoids this bundle.
    """
    if not np.any(rib_mask):
        return np.zeros_like(rib_mask, dtype=bool)

    spacing = spatial_orientation.spacing
    # Dilate inferiorly (towards caudal / -Z direction) by 4mm
    dz = spacing[2]
    k_steps = max(1, int(round(inferior_buffer_mm / dz)))

    struct = np.zeros((3, 3, 3), dtype=bool)
    struct[1, 1, 0] = True  # Shift strictly in -Z direction
    
    dilated = ndimage.binary_dilation(rib_mask, structure=struct, iterations=k_steps)
    # The risk zone is the space directly inferior to the rib, excluding the rib bone itself
    risk_zone = dilated & (~rib_mask)
    return risk_zone
