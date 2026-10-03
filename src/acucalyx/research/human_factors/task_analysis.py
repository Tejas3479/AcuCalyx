"""
AcuCalyx Research: Critical Task Analysis & Use-Related Risk Analysis (URRA) (IEC 62366-1 / ISO 14971:2019)

Governing Requirement: Frozen Plan v6.1 (Section 3 & Section 4)
Defines:
- Critical tasks C1 through C6 with foreseeable error modes and severity.
- Risk control mapping U1 through U6 designed to reduce use-related risk where reasonably practicable.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class CriticalTaskDefinition:
    """Definition of a safety-critical human task per FDA August 2026 Guidance."""
    task_id: str
    task_name: str
    user_group_ids: List[str]
    intended_action: str
    foreseeable_user_error: str
    clinical_harm: str
    hazard_severity: str  # 'Critical', 'High', 'Moderate'
    associated_risk_control_id: str


@dataclass(frozen=True)
class UseRelatedRiskAnalysisItem:
    """URRA traceability entry linking a foreseeable use error to a software risk control."""
    interlock_id: str
    error_mechanism: str
    software_risk_control: str
    risk_control_type: str  # 'Hard Modal Interlock', 'Visual Avatar Verification', 'Evidence Gating', etc.
    verification_method: str


STANDARD_CRITICAL_TASKS: Dict[str, CriticalTaskDefinition] = {
    "C1": CriticalTaskDefinition(
        task_id="C1",
        task_name="Lateralization Confirmation",
        user_group_ids=["attendings", "fellows"],
        intended_action="Verify and confirm patient target side (Left vs Right kidney) prior to access planning.",
        foreseeable_user_error="Inverting left vs right or accepting contralateral automated proposal.",
        clinical_harm="Percutaneous puncture of wrong kidney or non-target healthy organ (Catastrophic).",
        hazard_severity="Critical",
        associated_risk_control_id="U1"
    ),
    "C2": CriticalTaskDefinition(
        task_id="C2",
        task_name="Patient Surgical Position Verification",
        user_group_ids=["attendings", "fellows"],
        intended_action="Confirm operative table position (Prone vs Supine) matches planned trajectory transformation.",
        foreseeable_user_error="Planning in Supine coordinate space while operative setup is Prone.",
        clinical_harm="Trajectory inverted 180 degrees into anterior peritoneal viscera (Severe).",
        hazard_severity="High",
        associated_risk_control_id="U2"
    ),
    "C3": CriticalTaskDefinition(
        task_id="C3",
        task_name="Calyx Target & Papilla Confirmation",
        user_group_ids=["attendings", "fellows"],
        intended_action="Select and confirm entry via the papillary apex / target forniceal zone rather than neck.",
        foreseeable_user_error="Puncturing infundibular neck or directly into the renal pelvis.",
        clinical_harm="Interlobar or segmental arterial laceration; catastrophic retroperitoneal hemorrhage.",
        hazard_severity="Critical",
        associated_risk_control_id="U3"
    ),
    "C4": CriticalTaskDefinition(
        task_id="C4",
        task_name="C-Arm Gantry Angle Technologist Transfer",
        user_group_ids=["attendings", "technologists"],
        intended_action="Accurately communicate precomputed Bull's-Eye and Depth gantry angles to the technician.",
        foreseeable_user_error="Sign transposition: confusing LAO with RAO or Cranial with Caudal.",
        clinical_harm="Needle misdirected away from target calyx; excessive radiation; access failure.",
        hazard_severity="High",
        associated_risk_control_id="U4"
    ),
    "C5": CriticalTaskDefinition(
        task_id="C5",
        task_name="Depth Penetration Limit Monitoring",
        user_group_ids=["attendings"],
        intended_action="Monitor needle shaft 1-cm depth markers during advance to stop at calyx lumen.",
        foreseeable_user_error="Over-advancing needle past planned depth, disregarding depth graduation marks.",
        clinical_harm="Through-and-through counter-puncture of medial pelvis or hilar vasculature.",
        hazard_severity="High",
        associated_risk_control_id="U5"
    ),
    "C6": CriticalTaskDefinition(
        task_id="C6",
        task_name="Auditable Manual Override Logging",
        user_group_ids=["attendings"],
        intended_action="Document clinical rationale when modifying automated proposal and verify plan updates.",
        foreseeable_user_error="Modifying target without logging rationale or executing downstream stale plans.",
        clinical_harm="Compromised traceability; execution of unverified stale trajectory.",
        hazard_severity="Moderate",
        associated_risk_control_id="U6"
    )
}


STANDARD_URRA_MATRIX: Dict[str, UseRelatedRiskAnalysisItem] = {
    "U1": UseRelatedRiskAnalysisItem(
        interlock_id="U1",
        error_mechanism="Laterality Confusion / Wrong-Kidney Access",
        software_risk_control=(
            "Multi-Evidence Modal Gate: Enforces explicit clinician two-step confirmation displaying "
            "Left/Right label, Patient ID, CT scan laterality metadata, and 3D visual anatomical context (spine/liver)."
        ),
        risk_control_type="Hard Modal Interlock",
        verification_method="Deliberate wrong-side challenge cases in formative evaluation; blocks progression."
    ),
    "U2": UseRelatedRiskAnalysisItem(
        interlock_id="U2",
        error_mechanism="Surgical Orientation Mismatch (Prone vs Supine)",
        software_risk_control=(
            "5-Stage Transformation Tracking: Tracks CT acquisition context -> Planned Operative Position -> "
            "Explicit Clinician Confirmation -> Validated SE(3) Transform -> C-Arm Plan, accompanied by table mannequin avatar."
        ),
        risk_control_type="Visual Avatar Verification & Confirmation Gate",
        verification_method="Audit of rigid transformation matrix consistency against DICOM patient position."
    ),
    "U3": UseRelatedRiskAnalysisItem(
        interlock_id="U3",
        error_mechanism="Non-Opacified Calyx / Blind Puncture Risk",
        software_risk_control=(
            "Visibility Gate Evidence Badge: Calyx marked 'ESTIMATED_PRIOR' on unenhanced CT; enforces "
            "prominent spatial uncertainty cone and blocks autonomous optimal target claims."
        ),
        risk_control_type="Evidence-Based Gating & Uncertainty Badge",
        verification_method="Verification that unenhanced CT cases carry explicit ESTIMATED_PRIOR classification."
    ),
    "U4": UseRelatedRiskAnalysisItem(
        interlock_id="U4",
        error_mechanism="C-Arm Angle Miscommunication / Sign Transposition",
        software_risk_control=(
            "Technician Graphic Card & Closed-Loop Verbal Readback: Displays physical gantry diagram with "
            "color-coded tube orientation relative to prone patient, paired with structured readback protocol."
        ),
        risk_control_type="Technician Transfer Card & Verbal Readback Protocol",
        verification_method="Simulation study measuring transposition error rate under visual card vs readback."
    ),
    "U5": UseRelatedRiskAnalysisItem(
        interlock_id="U5",
        error_mechanism="Medial Counter-Puncture / Through-and-Through Perforation",
        software_risk_control=(
            "Case-Derived Depth Boundary: Dynamic threshold derived from patient calyx luminal depth and "
            "M3 metrology budget (U_95 = 1.64 mm), triggering flashing visual stop when needle nears medial wall."
        ),
        risk_control_type="Dynamic Anatomical Boundary Alarm",
        verification_method="Boundary triggering test: alarms activate before medial wall collision."
    ),
    "U6": UseRelatedRiskAnalysisItem(
        interlock_id="U6",
        error_mechanism="Stale Plan Execution After Upstream Modification",
        software_risk_control=(
            "Automated Stale Invalidation: Modifying any upstream input immediately flags downstream "
            "trajectories as 'STALE' and disables report export until recalculated."
        ),
        risk_control_type="State Machine Dependency Invalidation",
        verification_method="Verification that manual override transitions state to STALE and blocks PDF export."
    )
}
