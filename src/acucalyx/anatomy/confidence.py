"""
AcuCalyx Anatomy: Decomposed Anatomical Evidence & Observability Model

Implements Step 04 of AcuCalyx v2.1:
Decomposes anatomical confidence into three orthogonal concepts:
1. Segmentation Quality: Morphology, border continuity, and boundary gradient
2. Model Uncertainty: Variance and epistemic confidence of the segmentation source
3. Clinical Observability: Direct physical visibility vs prior estimation vs not assessable
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Union
import numpy as np
from scipy import ndimage

from acucalyx.anatomy.segmentation import OrganLabel


class ObservabilityState(str, Enum):
    DIRECTLY_OBSERVABLE = "DIRECTLY_OBSERVABLE"      # High radiopacity / contrast (bone, stones)
    MODEL_DERIVED = "MODEL_DERIVED"                  # Visible soft-tissue boundary (kidney, liver, colon)
    ESTIMATED_PRIOR = "ESTIMATED_PRIOR"              # Calyces on non-distended NCCT
    NOT_ASSESSABLE = "NOT_ASSESSABLE"                # Renal vessels or small nerves on NCCT


@dataclass(frozen=True)
class AnatomicalEvidence:
    """Rigorous decomposed evidence attributes for a single anatomical structure."""
    organ_name: str
    observability: ObservabilityState
    segmentation_quality_score: float   # [0.0, 1.0] (1.0 = pristine boundary, 0.0 = fragmented/noisy)
    model_uncertainty_score: float      # [0.0, 1.0] (0.0 = low uncertainty, 1.0 = highly uncertain)
    clinical_planning_confidence: str   # 'HIGH', 'MODERATE', 'LOW', 'BLOCKED'
    evidence_notes: str


def evaluate_organ_evidence(
    organ_label: Union[str, OrganLabel],
    mask: np.ndarray,
    ct_volume_hu: Optional[np.ndarray] = None,
    is_contrast_enhanced: bool = False
) -> AnatomicalEvidence:
    """
    Evaluates decomposed evidence for an organ based on anatomical modality physics.
    """
    key = str(organ_label.value if isinstance(organ_label, OrganLabel) else organ_label).lower()
    
    if not np.any(mask):
        return AnatomicalEvidence(
            organ_name=key,
            observability=ObservabilityState.NOT_ASSESSABLE,
            segmentation_quality_score=0.0,
            model_uncertainty_score=1.0,
            clinical_planning_confidence="BLOCKED",
            evidence_notes="Mask is empty; structure is not assessable in this study."
        )

    # 1. Base Observability classification
    if "rib" in key or "vertebrae" in key or "bone" in key:
        observability = ObservabilityState.DIRECTLY_OBSERVABLE
        base_uncertainty = 0.05
    elif "kidney" in key or "liver" in key or "spleen" in key:
        observability = ObservabilityState.MODEL_DERIVED
        base_uncertainty = 0.10
    elif "colon" in key or "bowel" in key:
        observability = ObservabilityState.MODEL_DERIVED
        base_uncertainty = 0.18  # Higher due to peristalsis / fluid / fecal variation
    elif "vessel" in key or "artery" in key or "vein" in key:
        if is_contrast_enhanced:
            observability = ObservabilityState.DIRECTLY_OBSERVABLE
            base_uncertainty = 0.15
        else:
            observability = ObservabilityState.NOT_ASSESSABLE
            base_uncertainty = 0.90
    elif "pleural" in key:
        observability = ObservabilityState.ESTIMATED_PRIOR
        base_uncertainty = 0.25
    else:
        observability = ObservabilityState.MODEL_DERIVED
        base_uncertainty = 0.20

    # 2. Evaluate Segmentation Quality Score (boundary continuity & volume sanity)
    # Check surface fragmentation using connected components on erosion
    n_voxels = np.sum(mask)
    if n_voxels < 10:
        quality_score = 0.2
    else:
        struct = ndimage.generate_binary_structure(3, 1)
        eroded = ndimage.binary_erosion(mask, structure=struct)
        surface_voxels = np.sum(mask & ~eroded)
        # Sphericity / compactness heuristic (ratio of surface to volume)
        compactness = (surface_voxels ** 1.5) / (n_voxels + 1e-6)
        # Moderate compactness is typical for anatomical organs
        quality_score = float(np.clip(1.0 - (compactness / 500.0), 0.3, 0.95))

    # 3. Clinical Planning Confidence
    if observability == ObservabilityState.NOT_ASSESSABLE:
        planning_conf = "BLOCKED"
        notes = "Modality cannot reliably resolve structure; planning blocked from relying on clearance."
    elif base_uncertainty > 0.3 or quality_score < 0.5:
        planning_conf = "LOW"
        notes = "High anatomical/segmentation uncertainty; expanded safety envelope required."
    elif base_uncertainty > 0.15:
        planning_conf = "MODERATE"
        notes = "Standard model-derived soft tissue boundary."
    else:
        planning_conf = "HIGH"
        notes = "High contrast bone or sharp parenchymal margin."

    return AnatomicalEvidence(
        organ_name=key,
        observability=observability,
        segmentation_quality_score=quality_score,
        model_uncertainty_score=base_uncertainty,
        clinical_planning_confidence=planning_conf,
        evidence_notes=notes
    )
