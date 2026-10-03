"""AcuCalyx DICOM PS 3.2 Interoperability Test Harness & SOP Contract Engine.

Verifies normative DICOM conformance contracts, non-ionizing Secondary Capture DRR
encoding policies, CT input operating envelope rejection, and PS 3.15 de-identification.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# Normative SOP Class UIDs
SOP_UID_CT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.2"
SOP_UID_ENHANCED_CT_STORAGE = "1.2.840.10008.5.1.4.1.1.2.1"
SOP_UID_SECONDARY_CAPTURE_STORAGE = "1.2.840.10008.5.1.4.1.1.7"
SOP_UID_MULTIFRAME_SC_STORAGE = "1.2.840.10008.5.1.4.1.1.7.2"
SOP_UID_XRAY_ANGIOGRAPHIC_STORAGE = "1.2.840.10008.5.1.4.1.1.12.1"
SOP_UID_STUDY_ROOT_FIND = "1.2.840.10008.5.1.4.1.2.2.1"
SOP_UID_STUDY_ROOT_MOVE = "1.2.840.10008.5.1.4.1.2.2.2"

# Transfer Syntaxes
TS_EXPLICIT_VR_LITTLE_ENDIAN = "1.2.840.10008.1.2.1"
TS_IMPLICIT_VR_LITTLE_ENDIAN = "1.2.840.10008.1.2"


@dataclass
class DicomDatasetMetadata:
    """Mock or actual DICOM dataset header representation for interoperability testing."""
    sop_class_uid: str
    transfer_syntax_uid: str
    patient_id: str
    patient_name: str
    gantry_tilt: float
    slice_thickness: float
    conversion_type: Optional[str] = None
    derivation_description: Optional[str] = None
    modality: str = "CT"


class DicomInteroperabilityHarness:
    """Automated test harness enforcing normative DICOM PS 3.2 and PS 3.15 rules."""

    def __init__(self, ae_title: str = "ACUCALYX_AE") -> None:
        self.ae_title = ae_title
        self.supported_storage_scp = {
            SOP_UID_CT_IMAGE_STORAGE: [TS_EXPLICIT_VR_LITTLE_ENDIAN, TS_IMPLICIT_VR_LITTLE_ENDIAN],
            SOP_UID_ENHANCED_CT_STORAGE: [TS_EXPLICIT_VR_LITTLE_ENDIAN],
        }
        self.supported_storage_scu = {
            SOP_UID_SECONDARY_CAPTURE_STORAGE: [TS_EXPLICIT_VR_LITTLE_ENDIAN],
            SOP_UID_MULTIFRAME_SC_STORAGE: [TS_EXPLICIT_VR_LITTLE_ENDIAN],
        }

    def evaluate_ct_ingestion_eligibility(
        self, dataset: DicomDatasetMetadata
    ) -> Tuple[bool, Optional[str]]:
        """Validate whether incoming CT dataset complies with the operating envelope."""
        if dataset.sop_class_uid not in self.supported_storage_scp:
            return False, f"ERR_UNSUPPORTED_SOP_CLASS: {dataset.sop_class_uid}"

        if dataset.transfer_syntax_uid not in self.supported_storage_scp[dataset.sop_class_uid]:
            return False, f"ERR_UNSUPPORTED_TRANSFER_SYNTAX: {dataset.transfer_syntax_uid}"

        if abs(dataset.gantry_tilt) > 0.001:
            return False, f"ERR_INPUT_REJECTED_GANTRY_TILT: Tilt {dataset.gantry_tilt}° violates 0.0° envelope."

        if dataset.slice_thickness > 2.5:
            return False, f"ERR_INPUT_REJECTED_SLICE_THICKNESS: Thickness {dataset.slice_thickness}mm > 2.5mm."

        return True, None

    def create_drr_secondary_capture_metadata(
        self,
        carm_angles_desc: str,
        patient_id: str,
        patient_name: str,
    ) -> DicomDatasetMetadata:
        """Create valid Secondary Capture metadata for synthetic DRR projection export."""
        return DicomDatasetMetadata(
            sop_class_uid=SOP_UID_SECONDARY_CAPTURE_STORAGE,
            transfer_syntax_uid=TS_EXPLICIT_VR_LITTLE_ENDIAN,
            patient_id=patient_id,
            patient_name=patient_name,
            gantry_tilt=0.0,
            slice_thickness=0.0,
            conversion_type="SYN",
            derivation_description=f"AcuCalyx DRR Rehearsal: {carm_angles_desc}",
            modality="OT",
        )

    def validate_drr_export_semantics(
        self, dataset: DicomDatasetMetadata
    ) -> Tuple[bool, Optional[str]]:
        """Verify that synthetic DRRs are never misclassified as live XA acquisitions."""
        if dataset.sop_class_uid == SOP_UID_XRAY_ANGIOGRAPHIC_STORAGE:
            return False, "SEMANTIC_VIOLATION: Reconstructed DRR must NOT be encoded as physical XA acquisition."

        if dataset.sop_class_uid != SOP_UID_SECONDARY_CAPTURE_STORAGE:
            return False, f"UNSUPPORTED_EXPORT_SOP: {dataset.sop_class_uid} is not Secondary Capture."

        if dataset.conversion_type != "SYN":
            return False, f"INVALID_CONVERSION_TYPE: Must be 'SYN' (synthesized), got {dataset.conversion_type}."

        return True, None

    def apply_ps315_deidentification(
        self,
        dataset: DicomDatasetMetadata,
        hmac_key: bytes = b"ACUCALYX_PS315_PSEUDONYMIZATION_KEY_2026",
    ) -> DicomDatasetMetadata:
        """Apply DICOM PS 3.15 Basic Application Level Confidentiality Profile."""
        # Cleanse direct identifiers
        pseudonym = hmac.new(
            hmac_key, dataset.patient_id.encode("utf-8"), hashlib.sha256
        ).hexdigest()[:16].upper()

        return DicomDatasetMetadata(
            sop_class_uid=dataset.sop_class_uid,
            transfer_syntax_uid=dataset.transfer_syntax_uid,
            patient_id=f"ANON_{pseudonym}",
            patient_name="ANONYMIZED^PATIENT",
            gantry_tilt=dataset.gantry_tilt,
            slice_thickness=dataset.slice_thickness,
            conversion_type=dataset.conversion_type,
            derivation_description=dataset.derivation_description,
            modality=dataset.modality,
        )
