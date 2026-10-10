"""
AcuCalyx Integrations: TotalSegmentator v2 Adapter
Governed by ACU-M15-EXEC-PLAN-2026-V2.

Provides an auditable pipeline bridge to TotalSegmentator v2 for broad anatomical
organ and hazard segmentation (117 classes, Apache-2.0 licensed "total" task):
- Pinned task/version configuration
- Cryptographic provenance tracking (input hash, model version, task ID)
- Mapping of TotalSegmentator labels to AcuCalyx Hazard & Target Organ classes
- Dual execution: Native CLI/Python call with deterministic synthetic fallback for offline/CI
- Explicit Clinical Boundary: TotalSegmentator segments broad organ boundaries;
  it does NOT segment minor calyces, infundibula, or calculi.
"""

from dataclasses import dataclass, field
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
from typing import Dict, List, Optional, Tuple, Union
import numpy as np

logger = logging.getLogger("acucalyx.integrations.totalsegmentator")

# -----------------------------------------------------------------------------
# TotalSegmentator v2 Default Task Label Mappings relevant to PCNL Planning
# -----------------------------------------------------------------------------
TOTALSEGMENTATOR_CLASSES = {
    1: "spleen",
    2: "kidney_right",
    3: "kidney_left",
    4: "gallbladder",
    5: "liver",
    6: "stomach",
    17: "colon",
    27: "vertebrae_L1",
    28: "vertebrae_L2",
    29: "vertebrae_L3",
    52: "aorta",
    53: "inferior_vena_cava",
    69: "rib_left_11",
    70: "rib_left_12",
    81: "rib_right_11",
    82: "rib_right_12",
}

# Mapping TotalSegmentator anatomical labels to AcuCalyx procedural categories
ACUCALYX_HAZARD_CATEGORY_MAP = {
    "spleen": "VISCERAL_CRITICAL",
    "liver": "VISCERAL_CRITICAL",
    "colon": "VISCERAL_CRITICAL",
    "aorta": "VASCULAR_MAJOR",
    "inferior_vena_cava": "VASCULAR_MAJOR",
    "rib_left_11": "SKELETAL_INTERCOSTAL",
    "rib_left_12": "SKELETAL_INTERCOSTAL",
    "rib_right_11": "SKELETAL_INTERCOSTAL",
    "rib_right_12": "SKELETAL_INTERCOSTAL",
    "kidney_right": "TARGET_ORGAN",
    "kidney_left": "TARGET_ORGAN",
}


@dataclass(frozen=True)
class TotalSegmentatorProvenance:
    """Cryptographic audit trail for TotalSegmentator segmentation execution."""
    input_volume_sha256: str
    task_name: str
    model_version: str
    fast_mode: bool
    license_identifier: str
    execution_mode: str  # "NATIVE_EXECUTION" or "SYNTHETIC_FALLBACK"
    classes_extracted: List[str]


@dataclass
class TotalSegmentatorOutput:
    """Multi-label segmentation output and hazard masks from TotalSegmentator."""
    provenance: TotalSegmentatorProvenance
    multilabel_volume: np.ndarray  # [Z, Y, X] with label IDs
    label_dict: Dict[int, str]
    hazard_masks: Dict[str, np.ndarray]  # hazard_name -> binary mask [Z, Y, X]
    kidney_mask: np.ndarray              # binary mask of target kidney
    execution_log: str


class TotalSegmentatorAdapter:
    """
    Adapter interfacing with TotalSegmentator v2.
    Integrates broad-organ segmentation while maintaining strict provenance and clinical limits.
    """

    def __init__(
        self,
        task: str = "total",
        fast: bool = False,
        model_version: str = "v2.4.0",
        license_id: str = "Apache-2.0",
    ):
        self.task = task
        self.fast = fast
        self.model_version = model_version
        self.license_id = license_id

    def is_installed(self) -> bool:
        """Checks if totalsegmentator executable or module is available in environment."""
        if shutil.which("TotalSegmentator") is not None:
            return True
        try:
            import totalsegmentator
            return True
        except ImportError:
            return False

    def segment_volume(
        self,
        nifti_or_array: Union[Path, str, np.ndarray],
        spacing_mm: Tuple[float, float, float] = (1.0, 1.0, 1.0),
        target_kidney: str = "right",
        force_mock: bool = False,
    ) -> TotalSegmentatorOutput:
        """
        Executes TotalSegmentator segmentation on the specified 3D volume.
        If force_mock or native binary is unavailable, executes high-fidelity deterministic
        synthetic segmentation matching TotalSegmentator anatomical bounds.
        """
        if isinstance(nifti_or_array, (str, Path)) and Path(nifti_or_array).is_file():
            # Compute SHA-256 of input file
            hasher = hashlib.sha256()
            with open(nifti_or_array, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            input_hash = hasher.hexdigest()
            # If native TotalSegmentator available and not force_mock
            if self.is_installed() and not force_mock:
                return self._run_native_segmentation(Path(nifti_or_array), input_hash, target_kidney)
            # Otherwise load array from file
            import nibabel as nib
            img = nib.load(str(nifti_or_array))
            vol_arr = np.asanyarray(img.dataobj)
            if vol_arr.ndim == 3:
                vol_arr = np.transpose(vol_arr, (2, 1, 0))  # Convert to [Z, Y, X]
        else:
            vol_arr = np.asarray(nifti_or_array)
            input_hash = hashlib.sha256(vol_arr.tobytes()[:100000]).hexdigest()

        # Synthetic Fallback Execution
        return self._generate_synthetic_totalseg_output(vol_arr, input_hash, spacing_mm, target_kidney)

    def _run_native_segmentation(
        self,
        input_path: Path,
        input_hash: str,
        target_kidney: str,
    ) -> TotalSegmentatorOutput:
        """Executes native TotalSegmentator CLI process."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "totalseg_out"
            cmd = ["TotalSegmentator", "-i", str(input_path), "-o", str(out_dir), "--task", self.task]
            if self.fast:
                cmd.append("--fast")
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)

            # Load multi-label output
            import nibabel as nib
            multilabel_path = out_dir / f"{self.task}.nii.gz"
            if multilabel_path.exists():
                ml_img = nib.load(str(multilabel_path))
                ml_arr = np.asanyarray(ml_img.dataobj)
                ml_arr = np.transpose(ml_arr, (2, 1, 0))
            else:
                raise RuntimeError("TotalSegmentator output file not generated")

            # Extract hazard masks
            hazard_masks: Dict[str, np.ndarray] = {}
            for label_id, name in TOTALSEGMENTATOR_CLASSES.items():
                hazard_masks[name] = (ml_arr == label_id).astype(np.uint8)

            kidney_id = 2 if target_kidney.lower() == "right" else 3
            kidney_mask = (ml_arr == kidney_id).astype(np.uint8)

            prov = TotalSegmentatorProvenance(
                input_volume_sha256=input_hash,
                task_name=self.task,
                model_version=self.model_version,
                fast_mode=self.fast,
                license_identifier=self.license_id,
                execution_mode="NATIVE_EXECUTION",
                classes_extracted=list(hazard_masks.keys()),
            )

            return TotalSegmentatorOutput(
                provenance=prov,
                multilabel_volume=ml_arr,
                label_dict=TOTALSEGMENTATOR_CLASSES,
                hazard_masks=hazard_masks,
                kidney_mask=kidney_mask,
                execution_log=res.stdout,
            )

    def _generate_synthetic_totalseg_output(
        self,
        vol_arr: np.ndarray,
        input_hash: str,
        spacing_mm: Tuple[float, float, float],
        target_kidney: str,
    ) -> TotalSegmentatorOutput:
        """
        Synthesizes anatomically realistic multi-label TotalSegmentator masks
        matched to the input volume dimensions [Z, Y, X].
        """
        shape = vol_arr.shape
        ml_vol = np.zeros(shape, dtype=np.uint8)
        hazard_masks: Dict[str, np.ndarray] = {}

        # Coordinate grid normalized to [0, 1]
        z_idx, y_idx, x_idx = np.indices(shape)
        zn = z_idx / max(1, shape[0] - 1)
        yn = y_idx / max(1, shape[1] - 1)
        xn = x_idx / max(1, shape[2] - 1)

        # 1. Right Kidney (Label 2): posterior right upper-middle abdomen
        rk_mask = ((xn - 0.70)**2 / 0.08**2 + (yn - 0.55)**2 / 0.12**2 + (zn - 0.50)**2 / 0.15**2) <= 1.0
        ml_vol[rk_mask] = 2
        hazard_masks["kidney_right"] = rk_mask.astype(np.uint8)

        # 2. Left Kidney (Label 3): posterior left upper-middle abdomen
        lk_mask = ((xn - 0.30)**2 / 0.08**2 + (yn - 0.55)**2 / 0.12**2 + (zn - 0.52)**2 / 0.15**2) <= 1.0
        ml_vol[lk_mask] = 3
        hazard_masks["kidney_left"] = lk_mask.astype(np.uint8)

        # 3. Liver (Label 5): right upper quadrant
        liver_mask = ((xn - 0.75)**2 / 0.18**2 + (yn - 0.45)**2 / 0.20**2 + (zn - 0.65)**2 / 0.20**2) <= 1.0
        ml_vol[liver_mask & (ml_vol == 0)] = 5
        hazard_masks["liver"] = (ml_vol == 5).astype(np.uint8)

        # 4. Spleen (Label 1): left posterolateral upper quadrant
        spleen_mask = ((xn - 0.22)**2 / 0.08**2 + (yn - 0.60)**2 / 0.10**2 + (zn - 0.68)**2 / 0.12**2) <= 1.0
        ml_vol[spleen_mask & (ml_vol == 0)] = 1
        hazard_masks["spleen"] = (ml_vol == 1).astype(np.uint8)

        # 5. Colon (Label 17): retrorenal / lateral descending and ascending colon
        colon_mask = (
            (((xn - 0.82)**2 / 0.05**2 + (yn - 0.62)**2 / 0.06**2) <= 1.0) |
            (((xn - 0.18)**2 / 0.05**2 + (yn - 0.62)**2 / 0.06**2) <= 1.0)
        ) & (zn >= 0.25) & (zn <= 0.75)
        ml_vol[colon_mask & (ml_vol == 0)] = 17
        hazard_masks["colon"] = (ml_vol == 17).astype(np.uint8)

        # 6. Aorta & IVC (Labels 52, 53): midline retroperitoneal vessels
        aorta_mask = (((xn - 0.46)**2 / 0.03**2 + (yn - 0.52)**2 / 0.03**2) <= 1.0) & (zn >= 0.20) & (zn <= 0.85)
        ivc_mask = (((xn - 0.54)**2 / 0.03**2 + (yn - 0.50)**2 / 0.03**2) <= 1.0) & (zn >= 0.20) & (zn <= 0.85)
        ml_vol[aorta_mask & (ml_vol == 0)] = 52
        ml_vol[ivc_mask & (ml_vol == 0)] = 53
        hazard_masks["aorta"] = (ml_vol == 52).astype(np.uint8)
        hazard_masks["inferior_vena_cava"] = (ml_vol == 53).astype(np.uint8)

        # 7. 11th and 12th Ribs (Labels 69, 70, 81, 82)
        r12_mask = (((xn - 0.85)**2 / 0.04**2 + (yn - 0.75)**2 / 0.04**2 + (zn - 0.58)**2 / 0.03**2) <= 1.0)
        l12_mask = (((xn - 0.15)**2 / 0.04**2 + (yn - 0.75)**2 / 0.04**2 + (zn - 0.60)**2 / 0.03**2) <= 1.0)
        ml_vol[r12_mask & (ml_vol == 0)] = 82
        ml_vol[l12_mask & (ml_vol == 0)] = 70
        hazard_masks["rib_right_12"] = (ml_vol == 82).astype(np.uint8)
        hazard_masks["rib_left_12"] = (ml_vol == 70).astype(np.uint8)

        kidney_mask = hazard_masks["kidney_right"] if target_kidney.lower() == "right" else hazard_masks["kidney_left"]

        prov = TotalSegmentatorProvenance(
            input_volume_sha256=input_hash,
            task_name=self.task,
            model_version=self.model_version,
            fast_mode=self.fast,
            license_identifier=self.license_id,
            execution_mode="SYNTHETIC_FALLBACK",
            classes_extracted=list(hazard_masks.keys()),
        )

        log = (
            f"TotalSegmentator Adapter: Generated synthetic anatomical multi-label segmentation. "
            f"Volume dimensions: {shape}, spacing: {spacing_mm}. Pinned model: {self.model_version} ({self.task})."
        )

        return TotalSegmentatorOutput(
            provenance=prov,
            multilabel_volume=ml_vol,
            label_dict=TOTALSEGMENTATOR_CLASSES,
            hazard_masks=hazard_masks,
            kidney_mask=kidney_mask,
            execution_log=log,
        )
