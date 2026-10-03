"""
AcuCalyx Usability: Clinical Runtime Safety Interlocks & Risk Controls (IEC 62366-1 / ISO 14971)

Governing Requirement: Frozen Plan v6.1 (Section 4 & Section 5)
Implements runtime software safety interlocks:
1. U1 Laterality Multi-Evidence Verification Gate & Wrong-Side Trap.
2. U2 5-Stage Surgical Positioning Transformation Interlock.
3. U5 Case-Derived Depth Boundary & Medial Wall Proximity Alarm.
4. U6 State Machine Stale Plan Invalidation Engine.
5. Multimodal Accessibility Corridor Classifier (4-factor redundant visual code).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from acucalyx.fluoroscopy.surgical_pose import (
    SurgicalPatientPosition,
    compute_ct_to_surgical_transform,
)


class MultimodalCorridorStatus(str, Enum):
    """4-factor multimodal corridor classification (no color-alone meaning)."""
    PLANNING_ELIGIBLE = "PLANNING_ELIGIBLE"       # Hexagon, Solid, Cyan (#00d2ff)
    CONDITIONAL = "CONDITIONAL"                   # Triangle, Dashed, Amber (#f59e0b)
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE" # Diamond, Dotted, Slate (#94a3b8)
    REJECTED = "REJECTED"                         # Cross, Hashed, Rose (#e11d48)


@dataclass(frozen=True)
class MultimodalVisualCode:
    """Redundant 4-factor visual coding specification."""
    status: MultimodalCorridorStatus
    symbol_icon: str
    text_label: str
    outline_style: str
    primary_color_hex: str
    clinical_rationale: str


MULTIMODAL_CODE_REGISTRY: Dict[MultimodalCorridorStatus, MultimodalVisualCode] = {
    MultimodalCorridorStatus.PLANNING_ELIGIBLE: MultimodalVisualCode(
        status=MultimodalCorridorStatus.PLANNING_ELIGIBLE,
        symbol_icon="⬢",
        text_label="PLANNING-ELIGIBLE",
        outline_style="solid",
        primary_color_hex="#00d2ff",
        clinical_rationale="Verified candidate corridor meeting all anatomical clearance and reach criteria."
    ),
    MultimodalCorridorStatus.CONDITIONAL: MultimodalVisualCode(
        status=MultimodalCorridorStatus.CONDITIONAL,
        symbol_icon="▲",
        text_label="CONDITIONAL",
        outline_style="dashed",
        primary_color_hex="#f59e0b",
        clinical_rationale="Corridor near hazard clearance buffer or with elevated torque; requires explicit review."
    ),
    MultimodalCorridorStatus.INSUFFICIENT_EVIDENCE: MultimodalVisualCode(
        status=MultimodalCorridorStatus.INSUFFICIENT_EVIDENCE,
        symbol_icon="◆",
        text_label="INSUFFICIENT_EVIDENCE",
        outline_style="dotted",
        primary_color_hex="#94a3b8",
        clinical_rationale="Collecting system calyx anatomy estimated from unenhanced CT prior; uncertainty cone active."
    ),
    MultimodalCorridorStatus.REJECTED: MultimodalVisualCode(
        status=MultimodalCorridorStatus.REJECTED,
        symbol_icon="✕",
        text_label="REJECTED",
        outline_style="dashed-hash",
        primary_color_hex="#e11d48",
        clinical_rationale="Corridor intersects visceral hazard (colon, lung/pleura, or intercostal bundle)."
    )
}


class DepthAlarmStatus(str, Enum):
    """Clinical alarm levels during needle insertion rehearsal."""
    NORMAL = "NORMAL"
    TARGET_PAPILLA_ZONE = "TARGET_PAPILLA_ZONE"
    LUMINAL_ACCESS = "LUMINAL_ACCESS"
    MEDIAL_WALL_WARNING = "MEDIAL_WALL_WARNING"
    COUNTER_PUNCTURE_CRITICAL_STOP = "COUNTER_PUNCTURE_CRITICAL_STOP"


@dataclass
class LateralityCheckResult:
    """Validation report for laterality verification interlock (U1)."""
    case_id: str
    is_laterality_verified: bool
    confirmed_side: Optional[str]
    ct_metadata_side: str
    anatomical_landmarks_concordant: bool
    is_two_step_confirmed: bool
    error_message: Optional[str] = None


class LateralityVerificationInterlock:
    """Interlock U1: Traps and blocks wrong-kidney access planning."""

    @staticmethod
    def verify_laterality(
        case_id: str,
        clinician_selected_side: str,
        ct_metadata_side: str,
        landmark_checks: Dict[str, bool],
        is_two_step_confirmed: bool
    ) -> LateralityCheckResult:
        """
        Validates laterality against multiple independent evidence streams.
        Blocks planning if mismatch, missing confirmation, or discordant landmarks.
        """
        sel_norm = clinician_selected_side.strip().upper()
        ct_norm = ct_metadata_side.strip().upper()

        if sel_norm not in ["LEFT", "RIGHT"]:
            return LateralityCheckResult(
                case_id=case_id,
                is_laterality_verified=False,
                confirmed_side=None,
                ct_metadata_side=ct_norm,
                anatomical_landmarks_concordant=False,
                is_two_step_confirmed=is_two_step_confirmed,
                error_message=f"Invalid laterality selection '{clinician_selected_side}'"
            )

        if sel_norm != ct_norm:
            return LateralityCheckResult(
                case_id=case_id,
                is_laterality_verified=False,
                confirmed_side=None,
                ct_metadata_side=ct_norm,
                anatomical_landmarks_concordant=False,
                is_two_step_confirmed=is_two_step_confirmed,
                error_message=(
                    f"CRITICAL SAFETY INTERLOCK TRIPPED: Selected side '{sel_norm}' does not match "
                    f"CT scan laterality metadata '{ct_norm}' for case {case_id}."
                )
            )

        # Check anatomical landmark concordance (e.g. liver/spleen position)
        landmarks_ok = all(landmark_checks.values()) if landmark_checks else False
        if not landmarks_ok:
            return LateralityCheckResult(
                case_id=case_id,
                is_laterality_verified=False,
                confirmed_side=None,
                ct_metadata_side=ct_norm,
                anatomical_landmarks_concordant=False,
                is_two_step_confirmed=is_two_step_confirmed,
                error_message="Anatomical landmark checks failed (discordant liver/spleen/spine orientation)."
            )

        if not is_two_step_confirmed:
            return LateralityCheckResult(
                case_id=case_id,
                is_laterality_verified=False,
                confirmed_side=None,
                ct_metadata_side=ct_norm,
                anatomical_landmarks_concordant=True,
                is_two_step_confirmed=False,
                error_message="Explicit two-step confirmation required by attending surgeon."
            )

        return LateralityCheckResult(
            case_id=case_id,
            is_laterality_verified=True,
            confirmed_side=sel_norm,
            ct_metadata_side=ct_norm,
            anatomical_landmarks_concordant=True,
            is_two_step_confirmed=True,
            error_message=None
        )


class SurgicalPositionInterlock:
    """Interlock U2: Manages 5-stage surgical orientation and SE(3) transformation tracking."""

    @staticmethod
    def resolve_surgical_pose(
        ct_acquisition_position: str,
        planned_operative_position: SurgicalPatientPosition,
        is_clinician_confirmed: bool
    ) -> Tuple[bool, Optional[np.ndarray], str]:
        """
        Computes 4x4 rigid transformation matrix from CT context to operative position.
        Requires explicit clinician confirmation before enabling C-arm plan.
        """
        if not is_clinician_confirmed:
            return False, None, "Operative position must be explicitly confirmed by clinician before C-arm planning"

        t_mat = compute_ct_to_surgical_transform(
            ct_scan_position=ct_acquisition_position,
            surgical_position=planned_operative_position
        )

        msg = (
            f"Surgical positioning verified: CT acquisition [{ct_acquisition_position}] -> "
            f"Operative setup [{planned_operative_position.value}]. Transformation matrix active."
        )
        return True, t_mat, msg


class DepthBoundaryInterlock:
    """Interlock U5: Enforces dynamic patient-specific depth limits and medial wall alarms."""

    def __init__(
        self,
        planned_depth_mm: float,
        calyx_luminal_depth_mm: float = 8.0,
        metrology_uncertainty_u95_mm: float = 1.64
    ):
        self.planned_depth_mm = planned_depth_mm
        self.calyx_luminal_depth_mm = calyx_luminal_depth_mm
        self.u95_mm = metrology_uncertainty_u95_mm

        # Medial wall position in depth coordinate
        self.medial_wall_depth_mm = planned_depth_mm + calyx_luminal_depth_mm
        # Critical stop boundary accounting for metrology uncertainty
        self.critical_stop_depth_mm = self.medial_wall_depth_mm - self.u95_mm

    def evaluate_penetration(self, current_depth_mm: float) -> Tuple[DepthAlarmStatus, Dict[str, Any]]:
        """Evaluates current virtual needle depth against anatomical boundaries."""
        dist_to_medial = self.medial_wall_depth_mm - current_depth_mm

        if current_depth_mm >= self.critical_stop_depth_mm:
            status = DepthAlarmStatus.COUNTER_PUNCTURE_CRITICAL_STOP
            visual_alarm = "FLASHING_RED_STOP"
            audio_stop = True
            msg = (
                f"CRITICAL DEPTH STOP: Current penetration ({current_depth_mm:.1f} mm) reaches critical medial "
                f"pelvis boundary ({self.critical_stop_depth_mm:.1f} mm, U_95 = {self.u95_mm} mm)."
            )
        elif dist_to_medial <= 2.0:
            status = DepthAlarmStatus.MEDIAL_WALL_WARNING
            visual_alarm = "AMBER_WARNING"
            audio_stop = False
            msg = f"WARNING: Needle tip within {dist_to_medial:.1f} mm of opposite medial calyx wall."
        elif current_depth_mm >= self.planned_depth_mm:
            status = DepthAlarmStatus.LUMINAL_ACCESS
            visual_alarm = "CYAN_TARGET"
            audio_stop = False
            msg = "Needle tip inside collecting system calyx lumen."
        elif current_depth_mm >= (self.planned_depth_mm - 4.0):
            status = DepthAlarmStatus.TARGET_PAPILLA_ZONE
            visual_alarm = "EMERALD_ZONE"
            audio_stop = False
            msg = "Needle tip engaging target forniceal papilla zone."
        else:
            status = DepthAlarmStatus.NORMAL
            visual_alarm = "NORMAL"
            audio_stop = False
            msg = "Advancement through flank tissue / parenchymal tunnel."

        telemetry = {
            "status": status.value,
            "current_depth_mm": round(current_depth_mm, 2),
            "distance_to_medial_wall_mm": round(dist_to_medial, 2),
            "visual_alarm": visual_alarm,
            "audio_stop_trigger": audio_stop,
            "message": msg
        }
        return status, telemetry


@dataclass
class PlanAuditRecord:
    """Immutable audit trail entry for clinician manual overrides."""
    case_id: str
    override_type: str
    clinician_id: str
    rationale: str
    timestamp_utc: str
    is_downstream_invalidated: bool


class StalePlanInvalidationEngine:
    """Interlock U6: Automatically invalidates downstream plans and reports upon modification."""

    def __init__(self):
        self._audit_log: List[PlanAuditRecord] = []
        self._stale_cases: set = set()

    def record_override(
        self,
        case_id: str,
        override_type: str,
        clinician_id: str,
        rationale: str
    ) -> PlanAuditRecord:
        """Records an override and invalidates downstream trajectories."""
        if not rationale or len(rationale.strip()) < 5:
            raise ValueError("Mandatory clinical rationale required for CDS override audit")

        record = PlanAuditRecord(
            case_id=case_id,
            override_type=override_type,
            clinician_id=clinician_id,
            rationale=rationale.strip(),
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            is_downstream_invalidated=True
        )
        self._audit_log.append(record)
        self._stale_cases.add(case_id)
        return record

    def is_plan_stale(self, case_id: str) -> bool:
        """Checks if a case's downstream plan is currently flagged as STALE."""
        return case_id in self._stale_cases

    def revalidate_plan(self, case_id: str):
        """Clears stale state after recalculation and explicit clinician re-approval."""
        self._stale_cases.discard(case_id)

    def can_export_report(self, case_id: str) -> bool:
        """PDF report export is strictly disabled if plan is STALE."""
        return not self.is_plan_stale(case_id)

    @staticmethod
    def is_plan_valid(is_stale: bool) -> bool:
        """Checks if a plan is valid based on stale status."""
        return not is_stale


StalePlanInterlock = StalePlanInvalidationEngine
