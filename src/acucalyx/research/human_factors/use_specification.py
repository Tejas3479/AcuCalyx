"""
AcuCalyx Research: Human Factors Use Specification (IEC 62366-1:2015 / FDA August 2026)

Governing Requirement: Frozen Plan v6.1 (Section 2 & Section 3)
Defines:
- Medical device intended use, user profiles, and operational environments.
- Decision authority invariants and CDS product boundary definitions.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple


class UserRoleCategory(str, Enum):
    """Recognized user population categories per IEC 62366-1:2015."""
    ATTENDING_ENDOUROLOGIST = "attendings"
    FELLOW_OR_RESIDENT = "fellows"
    JUNIOR_RESIDENT = "residents"
    RADIOLOGIC_TECHNOLOGIST = "technologists"
    OR_CIRCULATING_NURSE = "circulators"


@dataclass(frozen=True)
class UserPopulationProfile:
    """Characteristics and qualifications of a distinct user population."""
    role_name: str
    user_group_id: str
    education_level: str
    pcnl_experience_level: str
    key_responsibilities: List[str]
    physical_and_sensory_abilities: str = "Normal or corrected-to-normal visual acuity and color perception"


@dataclass(frozen=True)
class UseEnvironment:
    """Physical and environmental operating conditions."""
    environment_id: str
    name: str
    ambient_illuminance_lux_range: Tuple[float, float]
    viewing_distance_meters_range: Tuple[float, float]
    sterility_boundary: str
    environmental_distractors: List[str]


@dataclass
class AcuCalyxUseSpecification:
    """Comprehensive Use Specification per IEC 62366-1:2015 Clause 5.1."""
    intended_medical_indication: str
    scope_boundary_definition: str
    clinician_authority_model: str
    user_populations: Dict[str, UserPopulationProfile] = field(default_factory=dict)
    use_environments: Dict[str, UseEnvironment] = field(default_factory=dict)

    def validate_user_eligibility(self, group_id: str) -> bool:
        """Verifies if a user group is recognized in the authorized use specification."""
        return group_id in self.user_populations


# Standard Certified Specification per Frozen Plan v6.1
STANDARD_USE_SPECIFICATION = AcuCalyxUseSpecification(
    intended_medical_indication=(
        "Preoperative computational planning and virtual fluoroscopic rehearsal for adult patients "
        "undergoing planned percutaneous nephrolithotomy (PCNL) requiring percutaneous renal access planning, "
        "within the anatomical and imaging inclusion criteria of the study (informed by 2026 EAU Urolithiasis Guidelines)."
    ),
    scope_boundary_definition=(
        "Preoperative computational planning, virtual fluoroscopic rehearsal, and display of the validated plan "
        "as a clinician-controlled intraoperative reference. Explicitly does NOT provide automated intraoperative "
        "needle guidance, real-time tracking, or automatic C-arm actuation."
    ),
    clinician_authority_model=(
        "Clinician-in-the-Loop: The attending endourologist retains sole and final clinical authority "
        "to accept, modify, or reject any computational proposal or C-arm angle preset."
    ),
    user_populations={
        "attendings": UserPopulationProfile(
            role_name="Attending Endourologist",
            user_group_id="attendings",
            education_level="MD / Board-Certified in Urology",
            pcnl_experience_level="Expert (>100 lifetime PCNLs)",
            key_responsibilities=[
                "Confirm patient laterality and surgical positioning",
                "Review multi-objective Pareto trajectory trade-offs",
                "Approve or override candidate access paths",
                "Direct C-arm technologist positioning using closed-loop callouts"
            ]
        ),
        "fellows": UserPopulationProfile(
            role_name="Endourology Fellow / Senior Resident",
            user_group_id="fellows",
            education_level="MD / PGY 4-6",
            pcnl_experience_level="Intermediate (10-50 lifetime PCNLs)",
            key_responsibilities=[
                "Preoperative case ingestion and quality gate verification",
                "Initial trajectory corridor inspection",
                "Virtual needle advancement rehearsal",
                "Assisting attending surgeon with intraoperative plan review"
            ]
        ),
        "residents": UserPopulationProfile(
            role_name="Junior Urology Resident",
            user_group_id="residents",
            education_level="MD / PGY 1-3",
            pcnl_experience_level="Novice (<10 lifetime PCNLs)",
            key_responsibilities=[
                "CT upload and DICOM series selection",
                "Anatomical segmentation inspection",
                "Observing trajectory selection and rehearsal workflow"
            ]
        ),
        "technologists": UserPopulationProfile(
            role_name="Radiologic Technologist (C-Arm Operator)",
            user_group_id="technologists",
            education_level="Certified Radiologic Technologist (RT(R))",
            pcnl_experience_level="Technical C-arm positioning expert",
            key_responsibilities=[
                "Receive C-arm technician transfer card",
                "Execute closed-loop verbal readback of primary/secondary gantry angles",
                "Rotate and lock physical C-arm gantry at precomputed angles",
                "Enforce ALARA pulse rate presets (8 PPS) and collimation boundaries"
            ]
        )
    },
    use_environments={
        "office": UseEnvironment(
            environment_id="office",
            name="Preoperative Planning Workstation / Clinic Reading Room",
            ambient_illuminance_lux_range=(200.0, 500.0),
            viewing_distance_meters_range=(0.4, 0.9),
            sterility_boundary="Non-Sterile Desktop Console",
            environmental_distractors=["Telephone calls", "Colleague interruptions"]
        ),
        "operating_room": UseEnvironment(
            environment_id="operating_room",
            name="Endourology Operative Suite / Hybrid OR",
            ambient_illuminance_lux_range=(300.0, 600.0),
            viewing_distance_meters_range=(1.5, 3.5),
            sterility_boundary="Semi-Sterile Field / Wall-Mounted Dual Monitor",
            environmental_distractors=[
                "Surgical suction/irrigation noise",
                "Vital signs acoustic alarms",
                "Multiple personnel movements",
                "Subdued ambient lighting during endoscopic inspection"
            ]
        )
    }
)
