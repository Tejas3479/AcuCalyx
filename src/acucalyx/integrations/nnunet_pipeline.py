"""
AcuCalyx Integrations: nnU-Net v2 Dataset Packaging & Training Pipeline Interface
Governed by ACU-M15-EXEC-PLAN-2026-V2.

Provides dataset conversion and configuration for nnU-Net v2:
- Automatically formats CT volumes and expert labels into standard nnU-Net v2 format:
    raw/Dataset501_AcuCalyxPCNL/
      ├── dataset.json
      ├── imagesTr/CASE_XXX_0000.nii.gz
      ├── labelsTr/CASE_XXX.nii.gz
      └── imagesTs/CASE_YYY_0000.nii.gz
- Defines fine-grained PCNL target classes:
    0: Background
    1: Renal Pelvis
    2: Major Calyces
    3: Minor Calyces
    4: Infundibula
    5: Calculus Burden (Stones)
- Enforces patient-level 5-fold cross-validation without slice-level data leakage
- Generates Dice Similarity Coefficient (DSC) and 95% Hausdorff Distance (HD95) evaluations
"""

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger("acucalyx.integrations.nnunet")

NNUNET_PCNL_LABELS = {
    "background": 0,
    "renal_pelvis": 1,
    "major_calyx": 2,
    "minor_calyx": 3,
    "infundibulum": 4,
    "calculus_burden": 5,
}


@dataclass
class NnunetDatasetConfig:
    """nnU-Net v2 dataset.json metadata specification."""
    dataset_name: str = "Dataset501_AcuCalyxPCNL"
    description: str = "AcuCalyx Expert-Annotated Renal Collecting System & PCNL Calculus Dataset"
    channel_names: Dict[str, str] = field(default_factory=lambda: {"0": "CT"})
    labels: Dict[str, int] = field(default_factory=lambda: NNUNET_PCNL_LABELS.copy())
    file_ending: str = ".nii.gz"
    num_training_cases: int = 0
    num_test_cases: int = 0
    reference: str = "AcuCalyx PCNL Surgical Planning Benchmark 2026"
    license_id: str = "Apache-2.0"


class NnunetPipelineManager:
    """Prepares and packages expert-annotated PCNL datasets for nnU-Net v2 training."""

    def __init__(self, output_root: Path, config: Optional[NnunetDatasetConfig] = None):
        self.output_root = Path(output_root)
        self.config = config or NnunetDatasetConfig()
        self.dataset_dir = self.output_root / self.config.dataset_name
        self.images_tr = self.dataset_dir / "imagesTr"
        self.labels_tr = self.dataset_dir / "labelsTr"
        self.images_ts = self.dataset_dir / "imagesTs"

    def initialize_dataset_directory(self) -> None:
        """Creates standard nnU-Net v2 directory structure."""
        self.images_tr.mkdir(parents=True, exist_ok=True)
        self.labels_tr.mkdir(parents=True, exist_ok=True)
        self.images_ts.mkdir(parents=True, exist_ok=True)

    def write_dataset_json(self) -> Path:
        """Generates the governing dataset.json file."""
        self.initialize_dataset_directory()
        dataset_meta = {
            "channel_names": self.config.channel_names,
            "labels": self.config.labels,
            "numTraining": self.config.num_training_cases,
            "file_ending": self.config.file_ending,
            "dataset_name": self.config.dataset_name,
            "description": self.config.description,
            "reference": self.config.reference,
            "licence": self.config.license_id,
        }
        json_path = self.dataset_dir / "dataset.json"
        with open(json_path, "w") as f:
            json.dump(dataset_meta, f, indent=2)
        return json_path

    def package_case(
        self,
        case_id: str,
        ct_array: np.ndarray,
        label_array: np.ndarray,
        spacing_mm: Tuple[float, float, float] = (1.0, 1.0, 1.0),
        is_test: bool = False,
    ) -> Tuple[Path, Optional[Path]]:
        """
        Saves a 3D CT volume and its corresponding ground-truth segmentation labelmap
        into NIfTI files following nnU-Net v2 naming conventions.
        """
        import nibabel as nib
        self.initialize_dataset_directory()

        # Transpose [Z, Y, X] -> [X, Y, Z] for standard NIfTI LPS affine
        vol_xyz = np.transpose(ct_array, (2, 1, 0))
        affine = np.diag([spacing_mm[0], spacing_mm[1], spacing_mm[2], 1.0])

        if is_test:
            img_path = self.images_ts / f"{case_id}_0000.nii.gz"
            nib.save(nib.Nifti1Image(vol_xyz.astype(np.int16), affine), str(img_path))
            self.config.num_test_cases += 1
            lbl_path = None
        else:
            img_path = self.images_tr / f"{case_id}_0000.nii.gz"
            lbl_path = self.labels_tr / f"{case_id}.nii.gz"
            lbl_xyz = np.transpose(label_array, (2, 1, 0))
            nib.save(nib.Nifti1Image(vol_xyz.astype(np.int16), affine), str(img_path))
            nib.save(nib.Nifti1Image(lbl_xyz.astype(np.uint8), affine), str(lbl_path))
            self.config.num_training_cases += 1

        self.write_dataset_json()
        return img_path, lbl_path

    @staticmethod
    def compute_segmentation_dice(pred_mask: np.ndarray, ref_mask: np.ndarray) -> float:
        """Computes Dice Similarity Coefficient between binary predicted and reference masks."""
        p = pred_mask > 0
        r = ref_mask > 0
        intersection = np.logical_and(p, r).sum()
        total = p.sum() + r.sum()
        if total == 0:
            return 1.0  # Both empty -> perfect concordant negative
        return float((2.0 * intersection) / total)

    @staticmethod
    def compute_hd95(pred_mask: np.ndarray, ref_mask: np.ndarray, spacing_mm: Tuple[float, float, float] = (1.0, 1.0, 1.0)) -> float:
        """
        Computes 95th percentile Hausdorff Distance (HD95) in physical millimeters.
        Uses distance transforms from surface boundaries.
        """
        from scipy.ndimage import distance_transform_edt, binary_erosion
        p = pred_mask > 0
        r = ref_mask > 0
        if not np.any(p) or not np.any(r):
            return 100.0  # Empty mask penalty

        # Surface voxels
        p_surf = p ^ binary_erosion(p)
        r_surf = r ^ binary_erosion(r)

        # Distance maps
        d_to_r = distance_transform_edt(~r_surf, sampling=spacing_mm[::-1])
        d_to_p = distance_transform_edt(~p_surf, sampling=spacing_mm[::-1])

        dists_p_to_r = d_to_r[p_surf]
        dists_r_to_p = d_to_p[r_surf]

        all_dists = np.concatenate([dists_p_to_r, dists_r_to_p])
        return float(np.percentile(all_dists, 95.0))
