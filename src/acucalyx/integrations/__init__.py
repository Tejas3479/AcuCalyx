"""
AcuCalyx External Integrations Package
Governed by ACU-M15-EXEC-PLAN-2026-V2.

Exposes verified bridges to leading medical image computing frameworks:
- TotalSegmentator v2: Broad-organ and visceral/vascular hazard segmentation
- nnU-Net v2: PCNL collecting system supervised training pipeline
- 3D Slicer & MONAI Label: Expert reference annotation, QA & active learning
- VMTK: Centerline benchmarking & Voronoi comparison harness
"""

from acucalyx.integrations.totalsegmentator_adapter import (
    TotalSegmentatorAdapter,
    TotalSegmentatorProvenance,
    TotalSegmentatorOutput,
    TOTALSEGMENTATOR_CLASSES,
    ACUCALYX_HAZARD_CATEGORY_MAP,
)
from acucalyx.integrations.nnunet_pipeline import (
    NnunetPipelineManager,
    NnunetDatasetConfig,
    NNUNET_PCNL_LABELS,
)
from acucalyx.integrations.slicer_monailabel_bridge import (
    SlicerMonaiBridge,
    SLICER_PCNL_SEGMENT_DEFINITIONS,
    InterRaterConsensusReport,
    MonaiLabelClient,
)
from acucalyx.endoscopy.vmtk_benchmark import (
    VMTKBenchmarkHarness,
    CenterlineBenchmarkMetrics,
)
from acucalyx.geometry.simpleitk_bridge import (
    SpatialImageMetadata,
    numpy_to_sitk,
    sitk_to_numpy,
    resample_to_isotropic,
    compute_signed_maurer_distance_map,
    extract_largest_connected_component,
    binary_morphology,
)
from acucalyx.data.dataset_registry import (
    DatasetLicenseType,
    DatasetMetadataRecord,
    DATASET_REGISTRY,
    get_dataset_metadata,
    list_datasets,
)

__all__ = [
    "TotalSegmentatorAdapter",
    "TotalSegmentatorProvenance",
    "TotalSegmentatorOutput",
    "TOTALSEGMENTATOR_CLASSES",
    "ACUCALYX_HAZARD_CATEGORY_MAP",
    "NnunetPipelineManager",
    "NnunetDatasetConfig",
    "NNUNET_PCNL_LABELS",
    "SlicerMonaiBridge",
    "SLICER_PCNL_SEGMENT_DEFINITIONS",
    "InterRaterConsensusReport",
    "MonaiLabelClient",
    "VMTKBenchmarkHarness",
    "CenterlineBenchmarkMetrics",
    "SpatialImageMetadata",
    "numpy_to_sitk",
    "sitk_to_numpy",
    "resample_to_isotropic",
    "compute_signed_maurer_distance_map",
    "extract_largest_connected_component",
    "binary_morphology",
    "DatasetLicenseType",
    "DatasetMetadataRecord",
    "DATASET_REGISTRY",
    "get_dataset_metadata",
    "list_datasets",
]
