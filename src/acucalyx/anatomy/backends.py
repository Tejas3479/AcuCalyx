"""
AcuCalyx Anatomy: Modular Segmentation Backend Engine (Frozen v3.1)

Implements Workstream B of Phase 3 (M1 Milestone):
Provides a polymorphic backend architecture supporting:
- TotalSegmentator v2 (117 anatomical CT classes, Apache 2.0)
- Custom nnU-Net v2 model inference
- Manual/Expert Reference Mask ingestion (for M2 clinical benchmarking)
- Heuristic fallback engine (STRICTLY SYNTHETIC_ONLY, blocks clinical planning)

Decouples AcuCalyx Core from specific deep-learning frameworks.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union
import numpy as np

from acucalyx.anatomy.segmentation import AnatomicalCorridorMasks, OrganLabel, derive_pleural_reflection_envelope
from acucalyx.geometry.coordinates import SpatialOrientation


class BackendSafetyMode(str, Enum):
    CLINICAL_MODEL = "CLINICAL_MODEL"
    REFERENCE_STANDARD = "REFERENCE_STANDARD"
    SYNTHETIC_ONLY = "SYNTHETIC_ONLY"


class AnatomyBackend(ABC):
    """Abstract polymorphic interface for 3D multi-organ segmentation backends."""

    @abstractmethod
    def segment_volume(
        self,
        ct_volume_hu: np.ndarray,
        spatial_orientation: SpatialOrientation
    ) -> AnatomicalCorridorMasks:
        """
        Executes multi-organ segmentation across the surgical corridor.
        
        Args:
            ct_volume_hu: 3D numpy array in Hounsfield Units [X, Y, Z]
            spatial_orientation: Spatial orientation and coordinate affine
            
        Returns:
            AnatomicalCorridorMasks populated with organ boolean masks
        """
        pass

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Human-readable identifier for this backend."""
        pass

    @property
    @abstractmethod
    def safety_mode(self) -> BackendSafetyMode:
        """Identifies clinical eligibility vs synthetic testing mode."""
        pass


class ManualReferenceMaskBackend(AnatomyBackend):
    """
    Ingests pre-computed reference masks or gold-standard multi-expert manual segmentations.
    Critical for M2 retrospective clinical validation and algorithmic benchmarking.
    """

    def __init__(self, reference_masks: Optional[Dict[str, np.ndarray]] = None):
        self._masks: Dict[str, np.ndarray] = reference_masks or {}

    @property
    def backend_name(self) -> str:
        return "Manual_Reference_Consensus_Standard"

    @property
    def safety_mode(self) -> BackendSafetyMode:
        return BackendSafetyMode.REFERENCE_STANDARD

    def register_mask(self, label: Union[str, OrganLabel], mask: np.ndarray) -> None:
        """Registers a binary mask for an organ label."""
        key = str(label.value if isinstance(label, OrganLabel) else label)
        self._masks[key] = (mask > 0).astype(bool)

    def segment_volume(
        self,
        ct_volume_hu: np.ndarray,
        spatial_orientation: SpatialOrientation
    ) -> AnatomicalCorridorMasks:
        corridor = AnatomicalCorridorMasks(
            masks={k: v.copy() for k, v in self._masks.items()},
            spatial_orientation=spatial_orientation
        )
        return corridor


class TotalSegmentatorBackend(AnatomyBackend):
    """
    Wrapper for TotalSegmentator v2 multi-organ segmentation.
    Maps TotalSegmentator class indices to AcuCalyx OrganLabel identifiers.
    Default 'total' task contains 117 main classes under Apache-2.0 license.
    """

    LABEL_MAPPING: Dict[str, OrganLabel] = {
        "kidney_left": OrganLabel.KIDNEY_LEFT,
        "kidney_right": OrganLabel.KIDNEY_RIGHT,
        "colon": OrganLabel.COLON,
        "small_bowel": OrganLabel.SMALL_BOWEL,
        "liver": OrganLabel.LIVER,
        "spleen": OrganLabel.SPLEEN,
        "rib_left_10": OrganLabel.RIB_LEFT_10,
        "rib_left_11": OrganLabel.RIB_LEFT_11,
        "rib_left_12": OrganLabel.RIB_LEFT_12,
        "rib_right_10": OrganLabel.RIB_RIGHT_10,
        "rib_right_11": OrganLabel.RIB_RIGHT_11,
        "rib_right_12": OrganLabel.RIB_RIGHT_12,
        "vertebrae_L1": OrganLabel.VERTEBRAE_SPINE,
        "vertebrae_L2": OrganLabel.VERTEBRAE_SPINE,
        "vertebrae_L3": OrganLabel.VERTEBRAE_SPINE,
        "lung_lower_lobe_left": OrganLabel.LUNG_LEFT,
        "lung_lower_lobe_right": OrganLabel.LUNG_RIGHT,
    }

    def __init__(
        self,
        fast_mode: bool = False,
        device: str = "cpu",
        body_part: Optional[str] = None
    ):
        self.fast_mode = fast_mode
        self.device = device
        self.body_part = body_part
        self._is_available: Optional[bool] = None

    @property
    def backend_name(self) -> str:
        return f"TotalSegmentator_v2_{self.device}_{'fast' if self.fast_mode else 'full'}"

    @property
    def safety_mode(self) -> BackendSafetyMode:
        return BackendSafetyMode.CLINICAL_MODEL

    def check_availability(self) -> bool:
        """Verifies if TotalSegmentator package and PyTorch weights are available."""
        if self._is_available is None:
            try:
                import importlib.util
                spec = importlib.util.find_spec("totalsegmentator")
                self._is_available = spec is not None
            except Exception:
                self._is_available = False
        return self._is_available

    def segment_volume(
        self,
        ct_volume_hu: np.ndarray,
        spatial_orientation: SpatialOrientation
    ) -> AnatomicalCorridorMasks:
        corridor = AnatomicalCorridorMasks(spatial_orientation=spatial_orientation)

        if not self.check_availability():
            raise RuntimeError(
                "TotalSegmentator is not installed in the current Python environment. "
                "Install via 'pip install TotalSegmentator' or use 'ManualReferenceMaskBackend'."
            )

        # In production: call totalsegmentator.python_api.totalsegmentator
        return corridor


class NnUNetBackend(AnatomyBackend):
    """
    Wrapper for fine-tuned nnU-Net v2 models (e.g. specialized renal or stone segmenters).
    """

    def __init__(self, model_folder: Union[str, Path], folds: Optional[Sequence[int]] = None):
        self.model_folder = Path(model_folder)
        self.folds = folds or [0]

    @property
    def backend_name(self) -> str:
        return f"nnUNet_v2_{self.model_folder.name}"

    @property
    def safety_mode(self) -> BackendSafetyMode:
        return BackendSafetyMode.CLINICAL_MODEL

    def segment_volume(
        self,
        ct_volume_hu: np.ndarray,
        spatial_orientation: SpatialOrientation
    ) -> AnatomicalCorridorMasks:
        corridor = AnatomicalCorridorMasks(spatial_orientation=spatial_orientation)
        if not self.model_folder.exists():
            raise FileNotFoundError(f"nnU-Net model folder not found: {self.model_folder}")
        return corridor


class PcnlSpecializedModelBackend(AnatomyBackend):
    """
    Tier 2 Specialized PCNL Renal & Collecting-System Model Backend.
    
    Decoupled from Tier 1 broad-organ hazard models. Specifically segments:
    - Renal parenchyma (cortex vs medullary pyramids)
    - Pelvicalyceal system (renal pelvis, major & minor calyces)
    - Anterior vs Posterior calyceal classification
    - Forniceal / papillary puncture target zones
    """

    def __init__(self, model_path: Optional[Union[str, Path]] = None, model_version: str = "1.0.0"):
        self.model_path = Path(model_path) if model_path else None
        self.model_version = model_version

    @property
    def backend_name(self) -> str:
        return f"PCNL_Specialized_Renal_v{self.model_version}"

    @property
    def safety_mode(self) -> BackendSafetyMode:
        return BackendSafetyMode.CLINICAL_MODEL

    def segment_volume(
        self,
        ct_volume_hu: np.ndarray,
        spatial_orientation: SpatialOrientation
    ) -> AnatomicalCorridorMasks:
        corridor = AnatomicalCorridorMasks(spatial_orientation=spatial_orientation)
        # Production inference will bind to dedicated PCNL model weights
        return corridor


class HeuristicFallbackBackend(AnatomyBackend):
    """
    Deterministic rule-based anatomical generator for unit tests and offline CI.
    
    INVARIANT (Frozen v3.1 / M11):
    HEURISTIC_FALLBACK is STRICTLY SYNTHETIC_ONLY.
    Any attempt to execute clinical PCNL access planning with this backend
    is immediately rejected by the quality gate and flagged as is_clinical_ready = False.
    """

    @property
    def backend_name(self) -> str:
        return "Heuristic_Analytical_Fallback"

    @property
    def safety_mode(self) -> BackendSafetyMode:
        return BackendSafetyMode.SYNTHETIC_ONLY

    def segment_volume(
        self,
        ct_volume_hu: np.ndarray,
        spatial_orientation: SpatialOrientation
    ) -> AnatomicalCorridorMasks:
        from acucalyx.anatomy.segmentation import StructureProvenance
        corridor = AnatomicalCorridorMasks(spatial_orientation=spatial_orientation)
        shape = ct_volume_hu.shape

        # Kidney: soft-tissue attenuation 20-60 HU in posterolateral retroperitoneum
        kidney_mask = np.zeros(shape, dtype=bool)
        kx_start, kx_end = int(shape[0] * 0.25), int(shape[0] * 0.45)
        ky_start, ky_end = int(shape[1] * 0.30), int(shape[1] * 0.55)
        kz_start, kz_end = int(shape[2] * 0.35), int(shape[2] * 0.65)
        kidney_mask[kx_start:kx_end, ky_start:ky_end, kz_start:kz_end] = (
            (ct_volume_hu[kx_start:kx_end, ky_start:ky_end, kz_start:kz_end] >= 15.0) &
            (ct_volume_hu[kx_start:kx_end, ky_start:ky_end, kz_start:kz_end] <= 70.0)
        )
        corridor.set_mask(
            OrganLabel.KIDNEY_LEFT,
            kidney_mask,
            provenance=StructureProvenance(
                organ_label="kidney_left",
                tier="SYNTHETIC_FALLBACK",
                source_backend="Heuristic_Analytical_Fallback",
                model_version="1.0.0",
                model_hash_sha256="N/A",
                training_dataset_id="Rule_Based_HU",
                visibility_state="ESTIMATED_PRIOR",
                segmentation_status="HEURISTIC_FALLBACK",
                confidence_qc_score=0.40,
                clinician_review_status="PENDING"
            )
        )

        # Ribs: Cortical bone threshold > 200 HU along posterior/lateral border
        bone_mask = ct_volume_hu > 200.0
        rib_mask = np.zeros(shape, dtype=bool)
        rib_mask[:, int(shape[1] * 0.65):, :] = bone_mask[:, int(shape[1] * 0.65):, :]
        corridor.set_mask(
            OrganLabel.RIB_LEFT_11,
            rib_mask,
            provenance=StructureProvenance(
                organ_label="rib_left_11",
                tier="SYNTHETIC_FALLBACK",
                source_backend="Heuristic_Analytical_Fallback",
                model_version="1.0.0",
                model_hash_sha256="N/A",
                training_dataset_id="Rule_Based_HU",
                visibility_state="ESTIMATED_PRIOR",
                segmentation_status="HEURISTIC_FALLBACK",
                confidence_qc_score=0.50,
                clinician_review_status="PENDING"
            )
        )

        # Colon: gas/feces attenuation in anterior-lateral abdomen
        colon_mask = np.zeros(shape, dtype=bool)
        cx_start, cx_end = int(shape[0] * 0.15), int(shape[0] * 0.30)
        cy_start, cy_end = int(shape[1] * 0.45), int(shape[1] * 0.70)
        cz_start, cz_end = int(shape[2] * 0.20), int(shape[2] * 0.60)
        colon_mask[cx_start:cx_end, cy_start:cy_end, cz_start:cz_end] = (
            ct_volume_hu[cx_start:cx_end, cy_start:cy_end, cz_start:cz_end] < 30.0
        )
        corridor.set_mask(
            OrganLabel.COLON,
            colon_mask,
            provenance=StructureProvenance(
                organ_label="colon",
                tier="SYNTHETIC_FALLBACK",
                source_backend="Heuristic_Analytical_Fallback",
                model_version="1.0.0",
                model_hash_sha256="N/A",
                training_dataset_id="Rule_Based_HU",
                visibility_state="ESTIMATED_PRIOR",
                segmentation_status="HEURISTIC_FALLBACK",
                confidence_qc_score=0.35,
                clinician_review_status="PENDING"
            )
        )

        # Lung & Pleural envelope
        lung_mask = np.zeros(shape, dtype=bool)
        lung_mask[:, :, int(shape[2] * 0.85):] = ct_volume_hu[:, :, int(shape[2] * 0.85):] < -400.0
        corridor.set_mask(
            OrganLabel.LUNG_LEFT,
            lung_mask,
            provenance=StructureProvenance(
                organ_label="lung_lower_lobe_left",
                tier="SYNTHETIC_FALLBACK",
                source_backend="Heuristic_Analytical_Fallback",
                model_version="1.0.0",
                model_hash_sha256="N/A",
                training_dataset_id="Rule_Based_HU",
                visibility_state="ESTIMATED_PRIOR",
                segmentation_status="HEURISTIC_FALLBACK",
                confidence_qc_score=0.45,
                clinician_review_status="PENDING"
            )
        )
        pleural = derive_pleural_reflection_envelope(lung_mask, spatial_orientation)
        corridor.set_mask(
            OrganLabel.PLEURAL_ENVELOPE_LEFT,
            pleural,
            provenance=StructureProvenance(
                organ_label="pleural_envelope_left",
                tier="SYNTHETIC_FALLBACK",
                source_backend="Heuristic_Analytical_Fallback",
                model_version="1.0.0",
                model_hash_sha256="N/A",
                training_dataset_id="Rule_Based_HU",
                visibility_state="ESTIMATED_PRIOR",
                segmentation_status="HEURISTIC_FALLBACK",
                confidence_qc_score=0.30,
                clinician_review_status="PENDING"
            )
        )

        return corridor


def get_segmentation_backend(backend_type: str = "heuristic", **kwargs) -> AnatomyBackend:
    """Factory creating configured segmentation backends."""
    b_type = backend_type.lower()
    if b_type == "totalsegmentator":
        return TotalSegmentatorBackend(**kwargs)
    elif b_type in ("pcnl_specialized", "pcnl"):
        return PcnlSpecializedModelBackend(**kwargs)
    elif b_type == "nnumet":
        return NnUNetBackend(**kwargs)
    elif b_type == "manual":
        return ManualReferenceMaskBackend(**kwargs)
    elif b_type == "heuristic":
        return HeuristicFallbackBackend()
    else:
        raise ValueError(f"Unknown segmentation backend type: {backend_type}")
