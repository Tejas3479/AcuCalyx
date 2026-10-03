"""AcuCalyx Regulatory Evidence Index & eSTAR v7.1 Section Taxonomy.

Maintains the controlled inventory of all Design & Development File (DDF),
Risk Management File (RMF), Software V&V, Benchtop, Cybersecurity, and
Clinical Feasibility artifacts mapped to FDA eSTAR dynamic subsections.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class EvidenceCategory(str, Enum):
    """Internal AcuCalyx regulatory evidence categories."""
    ADMINISTRATIVE = "E-01_ADMINISTRATIVE"
    DEVICE_DESCRIPTION = "E-02_DEVICE_DESCRIPTION"
    PREDICATE_LANDSCAPE = "E-03_PREDICATE_LANDSCAPE"
    LABELING_AND_IFU = "E-04_LABELING_AND_IFU"
    SOFTWARE_LIFECYCLE_VV = "E-05_SOFTWARE_LIFECYCLE_VV"
    CONFIGURATION_AND_SOUP = "E-06_CONFIGURATION_AND_SOUP"
    AIML_AND_PCCP = "E-07_AIML_AND_PCCP"
    RISK_MANAGEMENT = "E-08_RISK_MANAGEMENT"
    CYBERSECURITY = "E-09_CYBERSECURITY"
    HUMAN_FACTORS_USABILITY = "E-10_HUMAN_FACTORS_USABILITY"
    BENCHTOP_METROLOGY = "E-11_BENCHTOP_METROLOGY"
    CLINICAL_EVIDENCE = "E-12_CLINICAL_EVIDENCE"
    INTEROPERABILITY_DICOM = "E-13_INTEROPERABILITY_DICOM"
    POSTMARKET_READINESS = "E-14_POSTMARKET_READINESS"


@dataclass(frozen=True)
class EvidenceItem:
    """Individual regulatory evidence deliverable."""
    reference_id: str
    category: EvidenceCategory
    title: str
    relative_path: str
    governing_standard: str
    estar_section_mapping: str
    is_mandatory_for_submission: bool = True


class RegulatoryEvidenceCatalog:
    """Manages the controlled evidence index for FDA eSTAR premarket submissions."""

    def __init__(self) -> None:
        self._items: Dict[str, EvidenceItem] = {}
        self._initialize_default_catalog()

    def register_item(self, item: EvidenceItem) -> None:
        """Register an evidence deliverable in the catalog."""
        self._items[item.reference_id] = item

    def get_item(self, reference_id: str) -> Optional[EvidenceItem]:
        """Retrieve an evidence item by its reference ID."""
        return self._items.get(reference_id)

    def list_all_items(self) -> List[EvidenceItem]:
        """Return all registered evidence items."""
        return list(self._items.values())

    def get_items_by_category(self, category: EvidenceCategory) -> List[EvidenceItem]:
        """Return all evidence items belonging to a given category."""
        return [item for item in self._items.values() if item.category == category]

    def _initialize_default_catalog(self) -> None:
        """Populate the default AcuCalyx Core Milestone M7 evidence index."""
        defaults = [
            EvidenceItem(
                reference_id="DOC-REG-00",
                category=EvidenceCategory.ADMINISTRATIVE,
                title="Regulatory Strategy & Product Definition Freeze (Gate M4.5)",
                relative_path="docs/regulatory/00_M4_5_REGULATORY_STRATEGY_AND_PRODUCT_DEFINITION.md",
                governing_standard="21 CFR 892.2050 / FDA Pre-Sub",
                estar_section_mapping="eSTAR Section 1.0 (General & Administrative)",
            ),
            EvidenceItem(
                reference_id="DOC-REG-01",
                category=EvidenceCategory.DEVICE_DESCRIPTION,
                title="Design & Development Inputs / System Requirements Spec (SRS)",
                relative_path="docs/regulatory/01_DESIGN_AND_DEVELOPMENT_INPUTS_SRS.md",
                governing_standard="ISO 13485:2016 Clause 7.3.3",
                estar_section_mapping="eSTAR Section 2.0 (Device Description)",
            ),
            EvidenceItem(
                reference_id="DOC-REG-02",
                category=EvidenceCategory.SOFTWARE_LIFECYCLE_VV,
                title="Software Requirements Specification (SwRS) & 10-Tier RTM",
                relative_path="docs/regulatory/02_SOFTWARE_REQUIREMENTS_SPEC_SWRS.md",
                governing_standard="IEC 62304:2006 Clause 5.2 / FDA Enhanced Tier",
                estar_section_mapping="eSTAR Section 6.0 (Software Documentation)",
            ),
            EvidenceItem(
                reference_id="DOC-REG-03",
                category=EvidenceCategory.RISK_MANAGEMENT,
                title="ISO 14971 Risk Management File (PHA, SwFMEA, FTA, BRA)",
                relative_path="docs/regulatory/03_ISO_14971_RISK_MANAGEMENT_FILE.md",
                governing_standard="ISO 14971:2019 / ISO/TR 24971:2020",
                estar_section_mapping="eSTAR Section 9.0 (Risk Management)",
            ),
            EvidenceItem(
                reference_id="DOC-REG-04",
                category=EvidenceCategory.SOFTWARE_LIFECYCLE_VV,
                title="IEC 62304 Software Lifecycle, Safety Partitioning & Anomaly Process",
                relative_path="docs/regulatory/04_IEC_62304_SOFTWARE_LIFECYCLE_AND_SOUP.md",
                governing_standard="IEC 62304:2006 Clause 5 & Clause 9",
                estar_section_mapping="eSTAR Section 6.0 (Software Documentation)",
            ),
            EvidenceItem(
                reference_id="DOC-REG-05",
                category=EvidenceCategory.CYBERSECURITY,
                title="Cybersecurity Management Plan & SPDF Lifecycle Report",
                relative_path="docs/regulatory/05_CYBERSECURITY_MANAGEMENT_PLAN_AND_SPDF.md",
                governing_standard="FDA Premarket Cybersecurity (Feb 2026) / §524B",
                estar_section_mapping="eSTAR Section 7.0 (Cybersecurity)",
            ),
            EvidenceItem(
                reference_id="DOC-REG-06",
                category=EvidenceCategory.AIML_AND_PCCP,
                title="AI/ML Model Risk Management & Lifecycle Envelope",
                relative_path="docs/regulatory/06_AIML_MODEL_RISK_AND_LIFECYCLE.md",
                governing_standard="ISO/TS 24971-2:2026 & FDA PCCP Guidance",
                estar_section_mapping="eSTAR Section 8.0 (AI/ML Functions)",
            ),
            EvidenceItem(
                reference_id="DOC-REG-07",
                category=EvidenceCategory.PREDICATE_LANDSCAPE,
                title="Candidate Predicate Landscape & Substantial Equivalence Matrix",
                relative_path="docs/regulatory/07_PREMARKET_STRATEGY_AND_PREDICATES.md",
                governing_standard="21 CFR 807.87(f) / FDA 510(k) Guidance",
                estar_section_mapping="eSTAR Section 4.0 (Substantial Equivalence / De Novo)",
            ),
            EvidenceItem(
                reference_id="DOC-REG-08",
                category=EvidenceCategory.INTEROPERABILITY_DICOM,
                title="Normative DICOM PS 3.2 Conformance Statement",
                relative_path="docs/regulatory/08_DICOM_CONFORMANCE_STATEMENT_PS32.md",
                governing_standard="DICOM PS 3.2 (2026)",
                estar_section_mapping="eSTAR Section 13.0 (Interoperability)",
            ),
            EvidenceItem(
                reference_id="DOC-REG-09",
                category=EvidenceCategory.LABELING_AND_IFU,
                title="Clinician Cockpit Operator's Manual, IFU & 21 CFR 801 Labeling",
                relative_path="docs/regulatory/09_OPERATORS_MANUAL_AND_LABELING.md",
                governing_standard="21 CFR Part 801 / 21 CFR 801.109 / Part 830",
                estar_section_mapping="eSTAR Section 5.0 (Device Labeling)",
            ),
            EvidenceItem(
                reference_id="DOC-REG-10",
                category=EvidenceCategory.ADMINISTRATIVE,
                title="Internal Evidence Dossier Map for FDA non-IVD eSTAR v7.1",
                relative_path="docs/regulatory/10_PREMARKET_SUBMISSION_DOSSIER_MAP.md",
                governing_standard="FDA eSTAR Program (June 2026)",
                estar_section_mapping="eSTAR Master Assembly Index",
            ),
            EvidenceItem(
                reference_id="DOC-REG-11",
                category=EvidenceCategory.ADMINISTRATIVE,
                title="Design & Development Release Authorization Record (Gate M7)",
                relative_path="docs/regulatory/11_DESIGN_RELEASE_AUTHORIZATION_RECORD.md",
                governing_standard="ISO 13485:2016 Clause 7.3.7 / FDA QMSR",
                estar_section_mapping="eSTAR Section 2.0 (Design Controls Summary)",
            ),
            EvidenceItem(
                reference_id="DOC-REG-12",
                category=EvidenceCategory.AIML_AND_PCCP,
                title="TotalSegmentator v2 AI/ML System Inventory, Model Card & PCCP",
                relative_path="docs/regulatory/12_AIML_SYSTEM_INVENTORY_AND_MODEL_CARD.md",
                governing_standard="FDA Final PCCP Guidance (August 2025)",
                estar_section_mapping="eSTAR Section 8.0 (AI/ML Functions)",
            ),
            EvidenceItem(
                reference_id="DOC-REG-13",
                category=EvidenceCategory.CONFIGURATION_AND_SOUP,
                title="SOUP Management & Off-the-Shelf Software Evaluation Register",
                relative_path="docs/regulatory/13_SOUP_MANAGEMENT_AND_OTS_EVALUATION.md",
                governing_standard="IEC 62304 Clause 5.3.3 / Clause 8.1.2",
                estar_section_mapping="eSTAR Section 6.0 (Software Documentation)",
            ),
            EvidenceItem(
                reference_id="DOC-REG-14",
                category=EvidenceCategory.POSTMARKET_READINESS,
                title="Postmarket Surveillance, MDR (Part 803) & Corrections/Removals Plan",
                relative_path="docs/regulatory/14_POSTMARKET_SURVEILLANCE_AND_MDR_PLAN.md",
                governing_standard="21 CFR Part 803 / Part 806 / ISO 13485 Cl. 8",
                estar_section_mapping="eSTAR Section 14.0 (Postmarket Readiness)",
            ),
            EvidenceItem(
                reference_id="DOC-CLN-01",
                category=EvidenceCategory.CLINICAL_EVIDENCE,
                title="Investigational Protocol ACU-PILOT-01 (ISO 14155:2026)",
                relative_path="docs/clinical/01_INVESTIGATIONAL_PROTOCOL_ACU_PILOT_01.md",
                governing_standard="ISO 14155:2026 (Good Clinical Practice)",
                estar_section_mapping="eSTAR Section 12.0 (Clinical Evidence)",
            ),
            EvidenceItem(
                reference_id="DOC-CLN-02",
                category=EvidenceCategory.CLINICAL_EVIDENCE,
                title="Investigator's Brochure (IB) Compiling Pre-Clinical Metrology",
                relative_path="docs/clinical/02_INVESTIGATORS_BROCHURE_IB.md",
                governing_standard="ISO 14155:2026 Clause 6",
                estar_section_mapping="eSTAR Section 12.0 (Clinical Evidence)",
            ),
            EvidenceItem(
                reference_id="DOC-CLN-03",
                category=EvidenceCategory.CLINICAL_EVIDENCE,
                title="Feasibility Statistical Analysis Plan (SAP) & Estimand Spec",
                relative_path="docs/clinical/03_FEASIBILITY_STATISTICAL_ANALYSIS_PLAN.md",
                governing_standard="ISO 14155:2026 / ICH E9(R1)",
                estar_section_mapping="eSTAR Section 12.0 (Clinical Evidence)",
            ),
            EvidenceItem(
                reference_id="DOC-CLN-04",
                category=EvidenceCategory.CLINICAL_EVIDENCE,
                title="Clinical Events Committee (CEC) Safety Charter & Clavien-Dindo Criteria",
                relative_path="docs/clinical/04_CEC_AND_SAFETY_MONITORING_CHARTER.md",
                governing_standard="ISO 14155:2026 Clause 5.9",
                estar_section_mapping="eSTAR Section 12.0 (Clinical Evidence)",
            ),
            EvidenceItem(
                reference_id="DOC-CLN-05",
                category=EvidenceCategory.BENCHTOP_METROLOGY,
                title="Site Initiation & C-Arm Dry-Run Phantom Calibration Specification",
                relative_path="docs/clinical/05_SITE_INITIATION_AND_CALIBRATION_SPEC.md",
                governing_standard="ASTM F2554-22 / Site Quality Gate",
                estar_section_mapping="eSTAR Section 11.0 (Non-Clinical Benchtop)",
            ),
            EvidenceItem(
                reference_id="DOC-REG-15",
                category=EvidenceCategory.HUMAN_FACTORS_USABILITY,
                title="Human Factors & Summative Usability Engineering Report (IEC 62366-1)",
                relative_path="docs/regulatory/15_HUMAN_FACTORS_AND_USABILITY_ENGINEERING_REPORT.md",
                governing_standard="IEC 62366-1:2015+AMD1:2020 / FDA Aug 2026",
                estar_section_mapping="eSTAR Section 10.0 (Human Factors)",
            ),
        ]
        for item in defaults:
            self.register_item(item)
