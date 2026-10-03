"""
AcuCalyx Usability: C-Arm Operating Room Verbal Protocol & Communication Card (IEC 62366-1)

Governing Requirement: Frozen Plan v6.1 (Section 6.1)
Implements:
1. Standardized 4-step Closed-Loop Verbal Readback Protocol:
   Surgeon Directive -> Technician Readback -> Surgeon Confirmation -> Technician Gantry Lock.
2. Dynamic C-arm angle communication card generation per patient trajectory and hardware profile.
3. Automated transposition error detection engine (LAO/RAO sign inversion, CRAN/CAUD swap).
"""

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from acucalyx.fluoroscopy.carm_profile import CArmProfile, PHILIPS_ZENITION_70
from acucalyx.fluoroscopy.surgical_pose import (
    construct_bullseye_carm_pose,
    construct_depth_verification_carm_pose,
)
from acucalyx.geometry.transforms import LineSegment3D


class TranspositionErrorType(str, Enum):
    """Categorization of C-arm communication transfer errors."""
    NONE = "NONE"
    PRIMARY_ORBITAL_SIGN_INVERSION = "PRIMARY_ORBITAL_SIGN_INVERSION"  # e.g. LAO confused with RAO
    SECONDARY_ANGULATION_SIGN_INVERSION = "SECONDARY_ANGULATION_SIGN_INVERSION" # e.g. CRAN confused with CAUD
    COMPOUND_DOUBLE_SIGN_INVERSION = "COMPOUND_DOUBLE_SIGN_INVERSION"
    PRIMARY_SECONDARY_AXES_SWAPPED = "PRIMARY_SECONDARY_AXES_SWAPPED"
    MAGNITUDE_DISCREPANCY = "MAGNITUDE_DISCREPANCY"


@dataclass(frozen=True)
class VerbalProtocolScript:
    """Scripted 4-step closed-loop verbal interaction sequence."""
    step_1_directive: str
    step_2_readback: str
    step_3_confirmation: str
    step_4_verification: str


@dataclass(frozen=True)
class CarmVerbalProtocolCard:
    """Full technologist transfer card with ALARA presets and verbal protocol scripts."""
    case_id: str
    target_calyx_name: str
    carm_model: str
    bullseye_primary_angle_deg: float
    bullseye_secondary_angle_deg: float
    depth_primary_angle_deg: float
    depth_secondary_angle_deg: float
    recommended_pulse_rate_pps: int
    collimation_size_cm: Tuple[float, float]
    bullseye_verbal_script: VerbalProtocolScript
    depth_verbal_script: VerbalProtocolScript
    gantry_physical_tube_direction_hint: str


@dataclass
class CarmCommunicationEvaluationResult:
    """Report evaluating technician C-arm gantry angle entry against intended plan."""
    is_correct: bool
    transposition_error_type: TranspositionErrorType
    primary_error_deg: float
    secondary_error_deg: float
    total_angular_error_deg: float
    error_description: Optional[str] = None


class CarmCommunicationValidator:
    """
    Validates technologist manual gantry entry against intended precomputed plan,
    detecting sign inversion and axis transposition errors.
    """

    @staticmethod
    def evaluate_technician_entry(
        intended_primary_deg: float,
        intended_secondary_deg: float,
        entered_primary_deg: float,
        entered_secondary_deg: float,
        tolerance_deg: float = 1.0
    ) -> CarmCommunicationEvaluationResult:
        """
        Detects whether entered C-arm angles contain transposition errors:
        LAO (+) vs RAO (-), Cranial (+) vs Caudal (-), or swapped axes.
        """
        err_prim = entered_primary_deg - intended_primary_deg
        err_sec = entered_secondary_deg - intended_secondary_deg
        total_err = math.sqrt(err_prim**2 + err_sec**2)

        # Check exact or within tolerance
        if abs(err_prim) <= tolerance_deg and abs(err_sec) <= tolerance_deg:
            return CarmCommunicationEvaluationResult(
                is_correct=True,
                transposition_error_type=TranspositionErrorType.NONE,
                primary_error_deg=round(err_prim, 2),
                secondary_error_deg=round(err_sec, 2),
                total_angular_error_deg=round(total_err, 2),
                error_description=None
            )

        # Check axes swapped: (entered_primary ≈ intended_secondary) and (entered_secondary ≈ intended_primary)
        if (abs(entered_primary_deg - intended_secondary_deg) <= tolerance_deg and
            abs(entered_secondary_deg - intended_primary_deg) <= tolerance_deg):
            return CarmCommunicationEvaluationResult(
                is_correct=False,
                transposition_error_type=TranspositionErrorType.PRIMARY_SECONDARY_AXES_SWAPPED,
                primary_error_deg=round(err_prim, 2),
                secondary_error_deg=round(err_sec, 2),
                total_angular_error_deg=round(total_err, 2),
                error_description="CRITICAL TRANSPOSITION: Primary orbital angle and secondary angulation axes were swapped."
            )

        # Check sign inversions
        is_prim_inverted = abs(entered_primary_deg - (-intended_primary_deg)) <= tolerance_deg and abs(intended_primary_deg) > tolerance_deg
        is_sec_inverted = abs(entered_secondary_deg - (-intended_secondary_deg)) <= tolerance_deg and abs(intended_secondary_deg) > tolerance_deg

        if is_prim_inverted and is_sec_inverted:
            return CarmCommunicationEvaluationResult(
                is_correct=False,
                transposition_error_type=TranspositionErrorType.COMPOUND_DOUBLE_SIGN_INVERSION,
                primary_error_deg=round(err_prim, 2),
                secondary_error_deg=round(err_sec, 2),
                total_angular_error_deg=round(total_err, 2),
                error_description="CRITICAL TRANSPOSITION: Both LAO/RAO and Cranial/Caudal sign conventions were inverted."
            )
        elif is_prim_inverted:
            return CarmCommunicationEvaluationResult(
                is_correct=False,
                transposition_error_type=TranspositionErrorType.PRIMARY_ORBITAL_SIGN_INVERSION,
                primary_error_deg=round(err_prim, 2),
                secondary_error_deg=round(err_sec, 2),
                total_angular_error_deg=round(total_err, 2),
                error_description="CRITICAL TRANSPOSITION: LAO vs RAO sign inverted (beam oriented toward wrong lateral side)."
            )
        elif is_sec_inverted:
            return CarmCommunicationEvaluationResult(
                is_correct=False,
                transposition_error_type=TranspositionErrorType.SECONDARY_ANGULATION_SIGN_INVERSION,
                primary_error_deg=round(err_prim, 2),
                secondary_error_deg=round(err_sec, 2),
                total_angular_error_deg=round(total_err, 2),
                error_description="CRITICAL TRANSPOSITION: Cranial vs Caudal sign inverted."
            )
        else:
            return CarmCommunicationEvaluationResult(
                is_correct=False,
                transposition_error_type=TranspositionErrorType.MAGNITUDE_DISCREPANCY,
                primary_error_deg=round(err_prim, 2),
                secondary_error_deg=round(err_sec, 2),
                total_angular_error_deg=round(total_err, 2),
                error_description=f"Angle entry differs by {total_err:.1f} degrees without direct sign transposition."
            )


class CarmProtocolGenerator:
    """Generates standardized C-arm communication cards and scripts from planned trajectories."""

    @staticmethod
    def generate_card(
        case_id: str,
        target_calyx_name: str,
        planned_trajectory: LineSegment3D,
        carm_profile: CArmProfile = PHILIPS_ZENITION_70
    ) -> CarmVerbalProtocolCard:
        """Constructs standardized verbal callout card with dynamic angles."""
        be_pose = construct_bullseye_carm_pose(planned_trajectory, profile=carm_profile)
        dv_pose = construct_depth_verification_carm_pose(planned_trajectory, profile=carm_profile)

        be_prim = round(be_pose.gantry_primary_angle_deg, 1)
        be_sec = round(be_pose.gantry_secondary_angle_deg, 1)
        dv_prim = round(dv_pose.gantry_primary_angle_deg, 1)
        dv_sec = round(dv_pose.gantry_secondary_angle_deg, 1)

        be_prim_label = f"LAO {abs(be_prim)}°" if be_prim >= 0 else f"RAO {abs(be_prim)}°"
        be_sec_label = f"CRAN {abs(be_sec)}°" if be_sec >= 0 else f"CAUD {abs(be_sec)}°"

        dv_prim_label = f"LAO {abs(dv_prim)}°" if dv_prim >= 0 else f"RAO {abs(dv_prim)}°"
        dv_sec_label = f"CRAN {abs(dv_sec)}°" if dv_sec >= 0 else f"CAUD {abs(dv_sec)}°"

        be_script = VerbalProtocolScript(
            step_1_directive=f"Surgeon: 'AcuCalyx: Set Bull's-Eye View.'",
            step_2_readback=f"Technician: 'Bull's-Eye View: Primary {be_prim_label}, Secondary {be_sec_label}.'",
            step_3_confirmation=f"Surgeon: 'Confirmed: Rotate gantry to {be_prim_label}, {be_sec_label}.'",
            step_4_verification=f"Technician: 'Gantry locked at {be_prim_label}, {be_sec_label}. Ready for pulse fluoroscopy.'"
        )

        dv_script = VerbalProtocolScript(
            step_1_directive=f"Surgeon: 'AcuCalyx: Set Depth-Verification View.'",
            step_2_readback=f"Technician: 'Depth View: Primary {dv_prim_label}, Secondary {dv_sec_label}.'",
            step_3_confirmation=f"Surgeon: 'Confirmed: Rotate gantry to {dv_prim_label}, {dv_sec_label}.'",
            step_4_verification=f"Technician: 'Gantry locked at {dv_prim_label}, {dv_sec_label}. Ready for depth monitoring.'"
        )

        hint = f"Tube position: {be_prim_label}, {be_sec_label}; detector on opposite side of prone table."

        return CarmVerbalProtocolCard(
            case_id=case_id,
            target_calyx_name=target_calyx_name,
            carm_model=f"{carm_profile.manufacturer} {carm_profile.model_name}",
            bullseye_primary_angle_deg=be_prim,
            bullseye_secondary_angle_deg=be_sec,
            depth_primary_angle_deg=dv_prim,
            depth_secondary_angle_deg=dv_sec,
            recommended_pulse_rate_pps=8,
            collimation_size_cm=(15.0, 15.0),
            bullseye_verbal_script=be_script,
            depth_verbal_script=dv_script,
            gantry_physical_tube_direction_hint=hint
        )
