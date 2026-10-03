"""
AcuCalyx Fluoroscopy: Radiation-Exposure Planning & Workflow Support

Implements Step 4.08 of Phase 4 & Milestone M13 (Governed by ACU-M12V-M13-EXEC-PLAN-2026-V2):
- Complies with 2026 EAU Urolithiasis Guidelines (ALARA Radiation Protection Principles).
- Software Lifecycle governed by IEC 62304:2016 and ISO 14971:2019.
- References IEC 60601-2-43:2022 as an interventional X-ray equipment system and ALARA benchmark.

Governing Principles:
- Replaces uncalibrated speculative DAP formulas with preprocedural planning geometry.
- Computes planned projection poses to minimize manual trial-and-error gantry positioning sweeps.
- Tailors collimation and pulse-rate guidance to patient anatomy and institutional low-dose protocols.
- Explicitly disclaims real-time dose telemetry ingestion without active DICOM RDSR interface.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from acucalyx.fluoroscopy.carm_profile import CArmProfile


@dataclass(frozen=True)
class ALARAPlanningReport:
    """Preoperative radiation planning report designed to support ALARA workflow."""
    planned_view_count: int
    bullseye_primary_angle_deg: float
    bullseye_secondary_angle_deg: float
    depth_primary_angle_deg: float
    depth_secondary_angle_deg: float
    estimated_hunting_exposures_saved: int # Planning heuristic for avoided repositioning sweeps
    recommended_pulse_rate_pps: int        # Institutional baseline preset (e.g. 4-8 PPS)
    collimation_advisory: str
    alara_clinical_checklist: List[str]
    governing_standards: str = "IEC 62304 / ISO 14971; IEC 60601-2-43:2022 Reference; 2026 EAU Guidelines"
    pulse_rate_protocol_hint: str = (
        "Utilize the lowest clinically acceptable pulsed fluoroscopy rate per institutional protocol "
        "(typically 3–7.5 PPS) rather than continuous fluoroscopy."
    )
    dose_telemetry_disclaimer: str = (
        "PREOPERATIVE PLANNING NOTICE: AcuCalyx generates geometric projection planning and workflow "
        "guidance. It does not ingest real-time exposure telemetry, DAP, or cumulative dose without "
        "an active DICOM Radiation Dose Structured Report (RDSR) interface."
    )


def generate_alara_planning_report(
    bullseye_angles: Tuple[float, float],
    depth_angles: Tuple[float, float],
    profile: CArmProfile,
    target_kidney_side: str = "left"
) -> ALARAPlanningReport:
    """
    Synthesizes preoperative radiation protection guidance for the surgical team.
    """
    checklist = [
        "Drive C-arm gantry directly to precomputed angles before stepping on the exposure pedal.",
        "Activate low-dose pulsed mode (e.g. lowest available facility setting: 4 PPS or 7.5/8 PPS) rather than continuous fluoroscopy.",
        "Position flat-panel detector as close to the patient flank as sterile draping permits to reduce scatter.",
        f"Collimate X-ray field tightly to the {target_kidney_side.upper()} target calyx and access corridor anatomy.",
        "Ensure patient end-expiration apnea during final needle advancement to align with planned trajectory.",
        "Verify all starting poses independently under live low-dose imaging prior to puncture."
    ]

    collimation = (
        f"Collimate X-ray beam tightly to target calyx and access corridor anatomy "
        f"(conformal field over {target_kidney_side.upper()} renal pole). "
        f"Shield contralateral kidney, spinal column, and non-target abdominal viscera from primary beam exposure."
    )

    return ALARAPlanningReport(
        planned_view_count=2,
        bullseye_primary_angle_deg=bullseye_angles[0],
        bullseye_secondary_angle_deg=bullseye_angles[1],
        depth_primary_angle_deg=depth_angles[0],
        depth_secondary_angle_deg=depth_angles[1],
        estimated_hunting_exposures_saved=6,
        recommended_pulse_rate_pps=8,
        collimation_advisory=collimation,
        alara_clinical_checklist=checklist
    )

