"""
AcuCalyx Data: Public Medical Datasets & Reference Cohort Registry
Governed by ACU-M15-EXEC-PLAN-2026-V2 (Milestone M15.0).

Catalogues public kidney imaging datasets and AcuCalyx's expert reference cohort:
- Rigorous licensing audit (CC BY-NC-SA 4.0, CC BY 4.0, Open Access)
- Explicit PCNL collecting system suitability assessment
- Guards against invalid clinical or commercial use of research-only tumor datasets
- Defines AcuCalyx-PCNL-Ref-30 internal gold-standard benchmark specification
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class DatasetLicenseType(str, Enum):
    """Licensing governance for medical imaging datasets."""
    OPEN_COMMERCIAL_PERMITTED = "OPEN_COMMERCIAL_PERMITTED"  # CC BY 4.0, Apache-2.0
    NON_COMMERCIAL_RESEARCH_ONLY = "NON_COMMERCIAL_RESEARCH_ONLY"  # CC BY-NC-SA 4.0
    RESTRICTED_ACCESS_DUA = "RESTRICTED_ACCESS_DUA"  # Data Use Agreement required
    PROPRIETARY_CLINICAL_BENCHMARK = "PROPRIETARY_CLINICAL_BENCHMARK"  # Internal AcuCalyx reference


@dataclass(frozen=True)
class DatasetMetadataRecord:
    """Audit record for external public datasets and internal reference cohorts."""
    dataset_id: str
    name: str
    modality: str
    case_count: int
    license_type: DatasetLicenseType
    license_identifier: str
    collecting_system_annotated: bool
    calculi_annotated: bool
    intended_milestone_phase: str
    commercial_eligibility: bool
    clinical_limitations: str
    recommended_acucalyx_usage: str
    primary_citation: str


DATASET_REGISTRY: Dict[str, DatasetMetadataRecord] = {
    "KITS23": DatasetMetadataRecord(
        dataset_id="KITS23",
        name="Kidney and Kidney Tumor Segmentation Challenge 2023 (KiTS23)",
        modality="Abdominal CT (Arterial / Venous / Excretory)",
        case_count=489,
        license_type=DatasetLicenseType.NON_COMMERCIAL_RESEARCH_ONLY,
        license_identifier="CC BY-NC-SA 4.0",
        collecting_system_annotated=False,
        calculi_annotated=False,
        intended_milestone_phase="Research / Developmental Parenchymal Pretraining",
        commercial_eligibility=False,
        clinical_limitations=(
            "Labels restricted to renal parenchyma, tumor, and cyst. "
            "Does not contain minor calyx, infundibulum, or papillary puncture zone annotations."
        ),
        recommended_acucalyx_usage="Limited experimental pretraining of parenchymal outer boundary only. Not for core M15 reachability.",
        primary_citation="Heller et al., 'The KiTS23 Challenge Dataset', arXiv:2307.01975, 2023.",
    ),
    "TRUSTED": DatasetMetadataRecord(
        dataset_id="TRUSTED",
        name="Paired 3D Ultrasound and CT Kidney Dataset (TRUSTED)",
        modality="Transabdominal 3D Ultrasound + Abdominal CT",
        case_count=48,  # 96 kidneys
        license_type=DatasetLicenseType.OPEN_COMMERCIAL_PERMITTED,
        license_identifier="CC BY 4.0",
        collecting_system_annotated=False,
        calculi_annotated=False,
        intended_milestone_phase="Milestone M14 (US Simulation) & Milestone M16 (Multimodal Registration)",
        commercial_eligibility=True,
        clinical_limitations="Focuses on kidney capsule landmarks and US-CT registration. Lacks internal collecting-system calyx topology.",
        recommended_acucalyx_usage="Valuable for M14 probe pressure deformation and future M16 ultrasound registration; not for M15 reachability graph.",
        primary_citation="Scientific Data 12, Article 214, 2025. https://doi.org/10.1038/s41597-025-04467-1",
    ),
    "KSSD2025": DatasetMetadataRecord(
        dataset_id="KSSD2025",
        name="Kidney Stone Segmentation Dataset 2025 (KSSD2025)",
        modality="Non-Contrast Abdominal CT (NCCT)",
        case_count=120,
        license_type=DatasetLicenseType.RESTRICTED_ACCESS_DUA,
        license_identifier="Academic Data Use Agreement",
        collecting_system_annotated=False,
        calculi_annotated=True,
        intended_milestone_phase="Milestone M11 (Stones) & Milestone M15.4 (Stone Burden Volumetry)",
        commercial_eligibility=False,
        clinical_limitations="Annotates stone coordinates and volumes on NCCT; renal collecting system lumen not contrasted or segmented.",
        recommended_acucalyx_usage="Stone attenuation and volume validation benchmark.",
        primary_citation="International Journal of Computer Assisted Radiology and Surgery, 2025.",
    ),
    "ACUCALYX_PCNL_REF_30": DatasetMetadataRecord(
        dataset_id="ACUCALYX_PCNL_REF_30",
        name="AcuCalyx Expert-Annotated PCNL Collecting System Benchmark Cohort",
        modality="Contrast-Enhanced Volumetric CT Urography (Excretory Phase)",
        case_count=30,
        license_type=DatasetLicenseType.PROPRIETARY_CLINICAL_BENCHMARK,
        license_identifier="AcuCalyx Regulatory Evidence Baseline (ISO 14971 / IEC 62304)",
        collecting_system_annotated=True,
        calculi_annotated=True,
        intended_milestone_phase="Milestone M15.0 & M15.7 (M15-V Validation Gate)",
        commercial_eligibility=True,
        clinical_limitations="Curated clinical CT urography cases with triple-expert consensus annotations (lower/middle/upper calyces, infundibula, stones).",
        recommended_acucalyx_usage="The primary golden ground truth for AcuCalyx IPA, infundibular width, and endoscopic reachability validation.",
        primary_citation="AcuCalyx Clinical Evidence Dossier 2026, Document ACU-REF-PCNL-2026-V1.",
    ),
}


def get_dataset_metadata(dataset_id: str) -> DatasetMetadataRecord:
    """Retrieves dataset audit record by identifier."""
    key = dataset_id.upper()
    if key not in DATASET_REGISTRY:
        raise KeyError(f"Dataset '{dataset_id}' not found in registry. Available: {list(DATASET_REGISTRY.keys())}")
    return DATASET_REGISTRY[key]


def list_datasets(collecting_system_only: bool = False) -> List[DatasetMetadataRecord]:
    """Lists registered datasets, optionally filtering by collecting system annotation."""
    all_ds = list(DATASET_REGISTRY.values())
    if collecting_system_only:
        return [d for d in all_ds if d.collecting_system_annotated]
    return all_ds
