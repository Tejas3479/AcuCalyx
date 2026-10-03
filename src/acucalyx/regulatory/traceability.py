"""AcuCalyx 10-Tier Bidirectional Requirements Traceability Matrix (RTM) Engine.

Governed by ISO 13485:2016 Clause 7.3, IEC 62304 Clause 5.1.1, and FDA Premarket Software Guidance.
Enforces forward and backward closure across:
CN <-> UN <-> HAZ <-> RC <-> SRS <-> SwRS <-> ARCH <-> CODE <-> TEST <-> VAL
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class TraceabilityTier(str, Enum):
    """The 10 hierarchical tiers of the AcuCalyx Design & Development File."""

    CLINICAL_NEED = "CN"
    USER_NEED = "UN"
    HAZARD = "HAZ"
    RISK_CONTROL = "RC"
    SYSTEM_REQUIREMENT = "SRS"
    SOFTWARE_REQUIREMENT = "SwRS"
    ARCHITECTURE = "ARCH"
    CODE_MODULE = "CODE"
    VERIFICATION_TEST = "TEST"
    VALIDATION_EVIDENCE = "VAL"


@dataclass
class TraceabilityNode:
    """Represents a discrete element within the traceability graph."""

    id: str
    tier: TraceabilityTier
    title: str
    description: str
    rationale: str = ""
    upstream_ids: Set[str] = field(default_factory=set)
    downstream_ids: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tier": self.tier.value,
            "title": self.title,
            "description": self.description,
            "rationale": self.rationale,
            "upstream_ids": sorted(list(self.upstream_ids)),
            "downstream_ids": sorted(list(self.downstream_ids)),
            "metadata": self.metadata,
        }


class TraceabilityEngine:
    """Manages graph construction, validation, and querying across all 10 tiers."""

    def __init__(self) -> None:
        self.nodes: Dict[str, TraceabilityNode] = {}

    def add_node(self, node: TraceabilityNode) -> None:
        self.nodes[node.id] = node

    def link(self, upstream_id: str, downstream_id: str) -> None:
        if upstream_id not in self.nodes:
            raise KeyError(f"Upstream node '{upstream_id}' not found in RTM registry.")
        if downstream_id not in self.nodes:
            raise KeyError(f"Downstream node '{downstream_id}' not found in RTM registry.")

        self.nodes[upstream_id].downstream_ids.add(downstream_id)
        self.nodes[downstream_id].upstream_ids.add(upstream_id)

    def get_node(self, node_id: str) -> Optional[TraceabilityNode]:
        return self.nodes.get(node_id)

    def forward_trace(self, start_id: str) -> List[List[str]]:
        """Traverse downstream links to discover all downstream leaf paths."""
        if start_id not in self.nodes:
            return []

        paths: List[List[str]] = []

        def _traverse(current_id: str, current_path: List[str]) -> None:
            node = self.nodes[current_id]
            if not node.downstream_ids:
                paths.append(list(current_path))
                return
            for downstream in sorted(node.downstream_ids):
                _traverse(downstream, current_path + [downstream])

        _traverse(start_id, [start_id])
        return paths

    def backward_trace(self, start_id: str) -> List[List[str]]:
        """Traverse upstream links to discover all upstream root paths."""
        if start_id not in self.nodes:
            return []

        paths: List[List[str]] = []

        def _traverse(current_id: str, current_path: List[str]) -> None:
            node = self.nodes[current_id]
            if not node.upstream_ids:
                paths.append(list(current_path))
                return
            for upstream in sorted(node.upstream_ids):
                _traverse(upstream, current_path + [upstream])

        _traverse(start_id, [start_id])
        return paths

    def validate_closure(self) -> Dict[str, Any]:
        """Verify that the RTM is completely closed with no orphan or dangling nodes."""
        orphans: List[str] = []
        unmitigated_hazards: List[str] = []
        untested_requirements: List[str] = []

        tier_counts = {tier.value: 0 for tier in TraceabilityTier}

        for node_id, node in self.nodes.items():
            tier_counts[node.tier.value] += 1

            # Root tier (CN) has no upstream; Leaf tier (VAL / TEST) has no downstream
            if node.tier != TraceabilityTier.CLINICAL_NEED and not node.upstream_ids:
                orphans.append(node_id)
            if node.tier not in (TraceabilityTier.VALIDATION_EVIDENCE, TraceabilityTier.VERIFICATION_TEST) and not node.downstream_ids:
                orphans.append(node_id)

            # Hazards must link to at least one Risk Control
            if node.tier == TraceabilityTier.HAZARD:
                has_rc = any(
                    self.nodes[down].tier == TraceabilityTier.RISK_CONTROL
                    for down in node.downstream_ids
                    if down in self.nodes
                )
                if not has_rc:
                    unmitigated_hazards.append(node_id)

            # Software Requirements must link to at least one Verification Test
            if node.tier == TraceabilityTier.SOFTWARE_REQUIREMENT:
                # Check downstream paths for a TEST node
                paths = self.forward_trace(node_id)
                has_test = any(
                    any(self.nodes[step].tier == TraceabilityTier.VERIFICATION_TEST for step in p)
                    for p in paths
                )
                if not has_test:
                    untested_requirements.append(node_id)

        is_closed = (
            len(orphans) == 0
            and len(unmitigated_hazards) == 0
            and len(untested_requirements) == 0
        )

        return {
            "is_closed": is_closed,
            "total_nodes": len(self.nodes),
            "tier_counts": tier_counts,
            "orphaned_nodes": sorted(list(set(orphans))),
            "unmitigated_hazards": sorted(unmitigated_hazards),
            "untested_requirements": sorted(untested_requirements),
        }

    def export_json(self) -> Dict[str, Any]:
        return {
            "nodes": {node_id: node.to_dict() for node_id, node in self.nodes.items()},
            "closure_status": self.validate_closure(),
        }

    def export_markdown_matrix(self) -> str:
        lines = [
            "# AcuCalyx™ Requirements Traceability Matrix (RTM)",
            "",
            "| Tier | ID | Title | Upstream Links | Downstream Links |",
            "|---|---|---|---|---|",
        ]
        for node in sorted(self.nodes.values(), key=lambda n: (n.tier.value, n.id)):
            up = ", ".join(sorted(node.upstream_ids)) or "*(Root)*"
            down = ", ".join(sorted(node.downstream_ids)) or "*(Leaf)*"
            lines.append(f"| {node.tier.value} | `{node.id}` | {node.title} | {up} | {down} |")
        return "\n".join(lines)


def build_acucalyx_default_rtm() -> TraceabilityEngine:
    """Constructs the canonical 10-tier AcuCalyx RTM covering M0 through M5."""
    engine = TraceabilityEngine()

    # Tier 1: Clinical Needs (CN)
    cn_nodes = [
        TraceabilityNode("CN-01", TraceabilityTier.CLINICAL_NEED, "Safe PCNL Puncture", "Surgeon needs safe access corridor avoiding colon, pleura, and vessels."),
        TraceabilityNode("CN-02", TraceabilityTier.CLINICAL_NEED, "Optimal Stone Clearance", "Access trajectory must maximize rigid nephroscope reach into calyces."),
        TraceabilityNode("CN-03", TraceabilityTier.CLINICAL_NEED, "Fluoroscopic Rehearsal", "Pre-calculated C-arm angles to minimize fluoroscopy sweeps and radiation."),
        TraceabilityNode("CN-04", TraceabilityTier.CLINICAL_NEED, "Wrong-Site Prevention", "Absolute prevention of contralateral or incorrect-calyx puncture."),
        TraceabilityNode("CN-05", TraceabilityTier.CLINICAL_NEED, "Data & Plan Integrity", "Zero tolerance for trajectory coordinate alteration or patient data leakage."),
    ]

    # Tier 2: User Needs (UN)
    un_nodes = [
        TraceabilityNode("UN-01", TraceabilityTier.USER_NEED, "Visceral Hazard Clearance", "System calculates distance fields to colon and pleura."),
        TraceabilityNode("UN-02", TraceabilityTier.USER_NEED, "Forniceal Alignment", "System targets papilla fornix coaxially along infundibular axis."),
        TraceabilityNode("UN-03", TraceabilityTier.USER_NEED, "C-Arm Angle Roadmap", "System computes Bullseye and Progression gantry angles."),
        TraceabilityNode("UN-04", TraceabilityTier.USER_NEED, "Laterality & Pose Certification", "System verifies laterality and patient surgical posture."),
        TraceabilityNode("UN-05", TraceabilityTier.USER_NEED, "Depth Warning", "System halts and alarms when needle approaches medial renal border."),
        TraceabilityNode("UN-06", TraceabilityTier.USER_NEED, "Tamper-Proof Plan", "System cryptographically binds plan coordinates and parameters."),
    ]

    # Tier 3: Hazards (HAZ)
    haz_nodes = [
        TraceabilityNode("HAZ-SURG-01", TraceabilityTier.HAZARD, "Colonic Perforation", "Needle transfixes retrorenal colon causing sepsis."),
        TraceabilityNode("HAZ-SURG-02", TraceabilityTier.HAZARD, "Pneumothorax / Hemothorax", "Supracostal needle violates pleural reflection."),
        TraceabilityNode("HAZ-SURG-03", TraceabilityTier.HAZARD, "Vascular Laceration", "Non-coaxial entry shears interlobar vessels."),
        TraceabilityNode("HAZ-SURG-04", TraceabilityTier.HAZARD, "Medial Counter-Puncture", "Needle traverses medial collecting system into aorta/IVC."),
        TraceabilityNode("HAZ-USE-01", TraceabilityTier.HAZARD, "Wrong-Side Puncture", "Contralateral kidney punctured due to laterality confusion."),
        TraceabilityNode("HAZ-CYB-01", TraceabilityTier.HAZARD, "Trajectory Tampering", "Malicious or corrupt edit of planning coordinates in transit."),
        TraceabilityNode("HAZ-RAD-01", TraceabilityTier.HAZARD, "Excessive Radiation Exposure", "Prolonged fluoroscopy time or suboptimal angles causes excess dose."),
    ]

    # Tier 4: Risk Controls (RC)
    rc_nodes = [
        TraceabilityNode("RC-01", TraceabilityTier.RISK_CONTROL, "Colon 15mm Buffer", "Enforces >=15mm distance field buffer to colon."),
        TraceabilityNode("RC-02", TraceabilityTier.RISK_CONTROL, "Pleural 10mm Buffer", "Enforces >=10mm buffer to pleura; scores infracostal paths."),
        TraceabilityNode("RC-03", TraceabilityTier.RISK_CONTROL, "Forniceal Coaxial Cone", "Restricts puncture entry to <=20 deg coaxial cone at fornix."),
        TraceabilityNode("RC-04", TraceabilityTier.RISK_CONTROL, "Depth Stop Alarm", "Alarms within 5mm of medial calyx border; max 150mm depth."),
        TraceabilityNode("RC-05", TraceabilityTier.RISK_CONTROL, "Tri-Modal Laterality Gate", "Requires DICOM + Centroid + Surgeon laterality consensus."),
        TraceabilityNode("RC-06", TraceabilityTier.RISK_CONTROL, "Canonical SHA-256 Fingerprint", "Cryptographically locks plan coordinates against tampering."),
        TraceabilityNode("RC-07", TraceabilityTier.RISK_CONTROL, "ALARA Angle Roadmap", "Pre-calculated C-arm angles and dose area product report."),
    ]

    # Tier 5: System Requirements (SRS)
    srs_nodes = [
        TraceabilityNode("SRS-001", TraceabilityTier.SYSTEM_REQUIREMENT, "CT Thickness Gate", "Axial slice thickness <= 3.0mm."),
        TraceabilityNode("SRS-003", TraceabilityTier.SYSTEM_REQUIREMENT, "Colon Clearance Spec", "Minimum 15.0mm colon clearance margin."),
        TraceabilityNode("SRS-004", TraceabilityTier.SYSTEM_REQUIREMENT, "Pleural Buffer Spec", "Minimum 10.0mm pleural clearance margin."),
        TraceabilityNode("SRS-005", TraceabilityTier.SYSTEM_REQUIREMENT, "Puncture Angle Spec", "Puncture angle <= 20.0 deg coaxial with calyx axis."),
        TraceabilityNode("SRS-008", TraceabilityTier.SYSTEM_REQUIREMENT, "C-Arm Envelope Spec", "LAO/RAO <= 45 deg, CRA/CAU <= 30 deg."),
        TraceabilityNode("SRS-009", TraceabilityTier.SYSTEM_REQUIREMENT, "Depth Limit Spec", "Max needle depth <= 150mm; medial counter-puncture alarm."),
        TraceabilityNode("SRS-010", TraceabilityTier.SYSTEM_REQUIREMENT, "Laterality Gate Spec", "Tri-modal laterality consensus before puncture."),
        TraceabilityNode("SRS-013", TraceabilityTier.SYSTEM_REQUIREMENT, "Plan Integrity Spec", "Canonical SHA-256 fingerprinting on plan JSON."),
        TraceabilityNode("SRS-016", TraceabilityTier.SYSTEM_REQUIREMENT, "ALARA Dose Spec", "Dose area product calculation and organ dose index."),
    ]

    # Tier 6: Software Requirements (SwRS)
    swrs_nodes = [
        TraceabilityNode("SwRS-002", TraceabilityTier.SOFTWARE_REQUIREMENT, "Slice Thickness Check", "Rejects scans with dz > 3.0mm."),
        TraceabilityNode("SwRS-006", TraceabilityTier.SOFTWARE_REQUIREMENT, "Hazard Clearance EDT", "Computes Euclidean distance fields and checks buffers."),
        TraceabilityNode("SwRS-007", TraceabilityTier.SOFTWARE_REQUIREMENT, "Forniceal Target Extraction", "Computes fornix coordinates and coaxial cone."),
        TraceabilityNode("SwRS-010", TraceabilityTier.SOFTWARE_REQUIREMENT, "C-Arm Angle Engine", "Computes Bullseye and Progression angles with limits."),
        TraceabilityNode("SwRS-012", TraceabilityTier.SOFTWARE_REQUIREMENT, "Radiation ALARA Model", "Estimates relative fluoroscopy dose and angles."),
        TraceabilityNode("SwRS-013", TraceabilityTier.SOFTWARE_REQUIREMENT, "Interlock U1 Laterality", "Enforces tri-modal laterality verification."),
        TraceabilityNode("SwRS-015", TraceabilityTier.SOFTWARE_REQUIREMENT, "Interlock U5 Depth Limit", "Triggers ALARM_COUNTER_PUNCTURE_CRITICAL."),
        TraceabilityNode("SwRS-018", TraceabilityTier.SOFTWARE_REQUIREMENT, "Plan Fingerprint Engine", "Serializes canonical JSON and computes SHA-256."),
    ]

    # Tier 7: Architecture Components (ARCH)
    arch_nodes = [
        TraceabilityNode("ARCH-INGESTION", TraceabilityTier.ARCHITECTURE, "DICOM Ingestion & QC", "Class C ingestion and geometric validation pipeline."),
        TraceabilityNode("ARCH-CORE-PLANNING", TraceabilityTier.ARCHITECTURE, "Safety Planning Core", "Class C trajectory optimizer and hazard avoidance engine."),
        TraceabilityNode("ARCH-INTERLOCKS", TraceabilityTier.ARCHITECTURE, "Runtime Safety Interlocks", "Class C/B runtime safety gates (U1–U6)."),
        TraceabilityNode("ARCH-CYBER", TraceabilityTier.ARCHITECTURE, "Cybersecurity & Integrity", "Class C cryptographic plan integrity and privacy subsystem."),
    ]

    # Tier 8: Code Modules (CODE)
    code_nodes = [
        TraceabilityNode("CODE-INGESTION", TraceabilityTier.CODE_MODULE, "acucalyx.ingestion.dicom", "DICOM parsing and quality gate implementation."),
        TraceabilityNode("CODE-HAZARDS", TraceabilityTier.CODE_MODULE, "acucalyx.geometry.hazard_zones", "Visceral hazard distance field computation."),
        TraceabilityNode("CODE-PLANNING", TraceabilityTier.CODE_MODULE, "acucalyx.planning.corridors", "Pareto trajectory optimization and coaxial cone."),
        TraceabilityNode("CODE-INTERLOCKS", TraceabilityTier.CODE_MODULE, "acucalyx.usability.interlocks", "Runtime safety interlocks U1, U2, U5, U6."),
        TraceabilityNode("CODE-CYBER", TraceabilityTier.CODE_MODULE, "acucalyx.regulatory.plan_integrity", "Canonical plan SHA-256 fingerprinting."),
        TraceabilityNode("CODE-FLUORO", TraceabilityTier.CODE_MODULE, "acucalyx.fluoroscopy.drr", "Virtual fluoroscopy and ALARA planning."),
    ]

    # Tier 9: Verification Tests (TEST)
    test_nodes = [
        TraceabilityNode("TEST-QGATE", TraceabilityTier.VERIFICATION_TEST, "test_quality_gate.py", "Verifies rejection of excessive thickness and gantry tilt."),
        TraceabilityNode("TEST-HAZARD", TraceabilityTier.VERIFICATION_TEST, "test_hazard_engine.py", "Verifies colon and pleural clearance buffers."),
        TraceabilityNode("TEST-CORRIDORS", TraceabilityTier.VERIFICATION_TEST, "test_planning_corridors.py", "Verifies coaxial cone and infundibular reach."),
        TraceabilityNode("TEST-INTERLOCK-U1", TraceabilityTier.VERIFICATION_TEST, "test_usability_engine.py::test_interlock_u1", "Verifies tri-modal laterality gate."),
        TraceabilityNode("TEST-INTERLOCK-U5", TraceabilityTier.VERIFICATION_TEST, "test_usability_engine.py::test_interlock_u5", "Verifies depth boundary alarm."),
        TraceabilityNode("TEST-ANTI-TAMPER", TraceabilityTier.VERIFICATION_TEST, "test_regulatory_and_cybersecurity.py::test_plan_integrity", "Verifies SHA-256 tampering trap."),
        TraceabilityNode("TEST-ALARA", TraceabilityTier.VERIFICATION_TEST, "test_drr_advanced.py::test_alara", "Verifies ALARA radiation dose calculation."),
    ]

    # Tier 10: Validation Evidence (VAL)
    val_nodes = [
        TraceabilityNode("VAL-M1-CT", TraceabilityTier.VALIDATION_EVIDENCE, "Milestone M1 Report", "Real-CT segmentation and quality gate validation."),
        TraceabilityNode("VAL-M2-CLINICAL", TraceabilityTier.VALIDATION_EVIDENCE, "Milestone M2 Report", "12-category retrospective challenge dataset validation."),
        TraceabilityNode("VAL-P4-CARM", TraceabilityTier.VALIDATION_EVIDENCE, "Milestone P4 Report", "Virtual fluoroscopy and C-arm projection validation."),
        TraceabilityNode("VAL-M3-PHANTOM", TraceabilityTier.VALIDATION_EVIDENCE, "Milestone M3 Report", "Physical anthropomorphic phantom accuracy (U95 = 1.64 mm)."),
        TraceabilityNode("VAL-M4-USABILITY", TraceabilityTier.VALIDATION_EVIDENCE, "Milestone M4 Report", "IEC 62366-1 human factors summative study with 4 user cohorts."),
        TraceabilityNode("VAL-M5-REGULATORY", TraceabilityTier.VALIDATION_EVIDENCE, "Milestone M5 Report", "Design controls and premarket cybersecurity verification."),
    ]

    all_nodes = (
        cn_nodes + un_nodes + haz_nodes + rc_nodes + srs_nodes
        + swrs_nodes + arch_nodes + code_nodes + test_nodes + val_nodes
    )

    for n in all_nodes:
        engine.add_node(n)

    # Establish full 10-tier links
    # CN -> UN
    engine.link("CN-01", "UN-01")
    engine.link("CN-02", "UN-02")
    engine.link("CN-03", "UN-03")
    engine.link("CN-04", "UN-04")
    engine.link("CN-01", "UN-05")
    engine.link("CN-05", "UN-06")

    # UN -> HAZ
    engine.link("UN-01", "HAZ-SURG-01")
    engine.link("UN-01", "HAZ-SURG-02")
    engine.link("UN-02", "HAZ-SURG-03")
    engine.link("UN-03", "HAZ-RAD-01")
    engine.link("UN-05", "HAZ-SURG-04")
    engine.link("UN-04", "HAZ-USE-01")
    engine.link("UN-06", "HAZ-CYB-01")

    # HAZ -> RC
    engine.link("HAZ-SURG-01", "RC-01")
    engine.link("HAZ-SURG-02", "RC-02")
    engine.link("HAZ-SURG-03", "RC-03")
    engine.link("HAZ-SURG-04", "RC-04")
    engine.link("HAZ-USE-01", "RC-05")
    engine.link("HAZ-CYB-01", "RC-06")
    engine.link("HAZ-RAD-01", "RC-07")

    # RC -> SRS
    engine.link("RC-01", "SRS-003")
    engine.link("RC-02", "SRS-004")
    engine.link("RC-03", "SRS-005")
    engine.link("RC-04", "SRS-009")
    engine.link("RC-05", "SRS-010")
    engine.link("RC-06", "SRS-013")
    engine.link("RC-07", "SRS-016")
    engine.link("RC-01", "SRS-001")
    engine.link("RC-03", "SRS-008")

    # SRS -> SwRS
    engine.link("SRS-001", "SwRS-002")
    engine.link("SRS-003", "SwRS-006")
    engine.link("SRS-004", "SwRS-006")
    engine.link("SRS-005", "SwRS-007")
    engine.link("SRS-008", "SwRS-010")
    engine.link("SRS-009", "SwRS-015")
    engine.link("SRS-010", "SwRS-013")
    engine.link("SRS-013", "SwRS-018")
    engine.link("SRS-016", "SwRS-012")

    # SwRS -> ARCH
    engine.link("SwRS-002", "ARCH-INGESTION")
    engine.link("SwRS-006", "ARCH-CORE-PLANNING")
    engine.link("SwRS-007", "ARCH-CORE-PLANNING")
    engine.link("SwRS-010", "ARCH-CORE-PLANNING")
    engine.link("SwRS-012", "ARCH-CORE-PLANNING")
    engine.link("SwRS-013", "ARCH-INTERLOCKS")
    engine.link("SwRS-015", "ARCH-INTERLOCKS")
    engine.link("SwRS-018", "ARCH-CYBER")

    # ARCH -> CODE
    engine.link("ARCH-INGESTION", "CODE-INGESTION")
    engine.link("ARCH-CORE-PLANNING", "CODE-HAZARDS")
    engine.link("ARCH-CORE-PLANNING", "CODE-PLANNING")
    engine.link("ARCH-CORE-PLANNING", "CODE-FLUORO")
    engine.link("ARCH-INTERLOCKS", "CODE-INTERLOCKS")
    engine.link("ARCH-CYBER", "CODE-CYBER")

    # CODE -> TEST
    engine.link("CODE-INGESTION", "TEST-QGATE")
    engine.link("CODE-HAZARDS", "TEST-HAZARD")
    engine.link("CODE-PLANNING", "TEST-CORRIDORS")
    engine.link("CODE-FLUORO", "TEST-ALARA")
    engine.link("CODE-INTERLOCKS", "TEST-INTERLOCK-U1")
    engine.link("CODE-INTERLOCKS", "TEST-INTERLOCK-U5")
    engine.link("CODE-CYBER", "TEST-ANTI-TAMPER")

    # TEST -> VAL
    engine.link("TEST-QGATE", "VAL-M1-CT")
    engine.link("TEST-HAZARD", "VAL-M2-CLINICAL")
    engine.link("TEST-CORRIDORS", "VAL-M3-PHANTOM")
    engine.link("TEST-ALARA", "VAL-P4-CARM")
    engine.link("TEST-INTERLOCK-U1", "VAL-M4-USABILITY")
    engine.link("TEST-INTERLOCK-U5", "VAL-M4-USABILITY")
    engine.link("TEST-ANTI-TAMPER", "VAL-M5-REGULATORY")

    return engine
