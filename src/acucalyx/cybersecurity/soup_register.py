"""AcuCalyx Auditable SOUP (Software of Unknown Provenance) Registry.

Governed by IEC 62304:2006 + AMD 1:2015 Clauses 5.3.3 & 8.1.2,
and FDA Premarket Cybersecurity Guidance (Feb 2026).
Maintains structured tracking of third-party dependencies, safety classifications,
functional requirements, known vulnerabilities, and verification test coverage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from acucalyx.regulatory.safety_boundary import SoftwareSafetyClass


@dataclass
class SOUPRecord:
    """Represents a formally qualified SOUP item per IEC 62304 Clause 5.3.3."""

    soup_id: str
    name: str
    version: str
    vendor: str
    safety_class: SoftwareSafetyClass
    functional_role: str
    system_prerequisites: str
    known_anomalies: List[str] = field(default_factory=list)
    cve_status: str = "NO_KNOWN_CRITICAL_CVES"
    verification_test_ids: List[str] = field(default_factory=list)
    update_policy: str = "QUALIFIED_PINNED_LOCKFILE"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "soup_id": self.soup_id,
            "name": self.name,
            "version": self.version,
            "vendor": self.vendor,
            "safety_class": self.safety_class.value,
            "functional_role": self.functional_role,
            "system_prerequisites": self.system_prerequisites,
            "known_anomalies": self.known_anomalies,
            "cve_status": self.cve_status,
            "verification_test_ids": self.verification_test_ids,
            "update_policy": self.update_policy,
        }


class SOUPRegistry:
    """Manages third-party software qualifications and audits test coverage."""

    def __init__(self) -> None:
        self.records: Dict[str, SOUPRecord] = self._load_default_soup()

    def _load_default_soup(self) -> Dict[str, SOUPRecord]:
        items = [
            SOUPRecord(
                soup_id="SOUP-01",
                name="torch",
                version="2.2.2",
                vendor="PyTorch Foundation",
                safety_class=SoftwareSafetyClass.CLASS_C,
                functional_role="Deep learning tensor calculations and segmentation inference.",
                system_prerequisites="CUDA 12.1+ or modern x86_64 CPU with AVX2.",
                known_anomalies=["Occasional non-deterministic float ordering on varying GPU architectures."],
                cve_status="CLEAN_PER_NVD_2026",
                verification_test_ids=["test_modular_anatomy_backends_and_safety_invariant"],
            ),
            SOUPRecord(
                soup_id="SOUP-02",
                name="SimpleITK",
                version="2.3.1",
                vendor="Insight Software Consortium",
                safety_class=SoftwareSafetyClass.CLASS_C,
                functional_role="3D Euclidean Distance Transform (EDT) and DICOM image IO.",
                system_prerequisites="Python 3.10+, 64-bit OS.",
                known_anomalies=[],
                cve_status="CLEAN_PER_NVD_2026",
                verification_test_ids=["test_hazard_clearance_and_intersection"],
            ),
            SOUPRecord(
                soup_id="SOUP-03",
                name="numpy",
                version="1.26.4",
                vendor="NumPy Developers",
                safety_class=SoftwareSafetyClass.CLASS_C,
                functional_role="LPS coordinate transformations and 3D affine matrix algebra.",
                system_prerequisites="Python 3.10+.",
                known_anomalies=[],
                cve_status="CLEAN_PER_NVD_2026",
                verification_test_ids=["test_dicom_affine_construction"],
            ),
            SOUPRecord(
                soup_id="SOUP-04",
                name="pydicom",
                version="2.4.4",
                vendor="PyDicom Team",
                safety_class=SoftwareSafetyClass.CLASS_C,
                functional_role="DICOM tag parsing, gantry tilt check, and PS 3.15 de-identification.",
                system_prerequisites="Python 3.10+.",
                known_anomalies=["v4.0 deprecation warnings for write_like_original and is_implicit_VR."],
                cve_status="CLEAN_PER_NVD_2026",
                verification_test_ids=["test_quality_gate_rejects_gantry_tilt", "test_dicom_ingestion_authoritative_spacing"],
            ),
            SOUPRecord(
                soup_id="SOUP-05",
                name="scipy",
                version="1.12.0",
                vendor="SciPy Developers",
                safety_class=SoftwareSafetyClass.CLASS_C,
                functional_role="Multi-objective Pareto frontier extraction and spatial KD-Tree queries.",
                system_prerequisites="Python 3.10+.",
                known_anomalies=[],
                cve_status="CLEAN_PER_NVD_2026",
                verification_test_ids=["test_extract_pareto_frontier"],
            ),
            SOUPRecord(
                soup_id="SOUP-06",
                name="fastapi",
                version="0.110.0",
                vendor="Tiangolo",
                safety_class=SoftwareSafetyClass.CLASS_B,
                functional_role="REST API gateway and clinician cockpit endpoints.",
                system_prerequisites="Python 3.10+.",
                known_anomalies=[],
                cve_status="CLEAN_PER_NVD_2026",
                verification_test_ids=["test_api_phantom_and_rehearsal_endpoints"],
            ),
            SOUPRecord(
                soup_id="SOUP-07",
                name="pydantic",
                version="2.6.4",
                vendor="Pydantic Team",
                safety_class=SoftwareSafetyClass.CLASS_B,
                functional_role="Data contract schemas, runtime boundary checks, and serialization.",
                system_prerequisites="Python 3.10+.",
                known_anomalies=[],
                cve_status="CLEAN_PER_NVD_2026",
                verification_test_ids=["test_use_specification_completeness"],
            ),
        ]
        return {r.soup_id: r for r in items}

    def get_soup(self, soup_id: str) -> Optional[SOUPRecord]:
        return self.records.get(soup_id)

    def list_all(self) -> List[SOUPRecord]:
        return sorted(list(self.records.values()), key=lambda r: r.soup_id)

    def audit_safety_coverage(self) -> Dict[str, Any]:
        """Verify that 100% of Class C SOUP dependencies have linked verification tests."""
        uncovered_class_c: List[str] = []

        for r in self.records.values():
            if r.safety_class == SoftwareSafetyClass.CLASS_C:
                if not r.verification_test_ids:
                    uncovered_class_c.append(r.soup_id)

        is_covered = len(uncovered_class_c) == 0
        return {
            "is_covered": is_covered,
            "total_soup_records": len(self.records),
            "uncovered_class_c_records": uncovered_class_c,
        }
