"""
AcuCalyx Endoscopy: Descriptive Access-Caliber Compatibility Profiles
Governed by ACU-M15-EXEC-PLAN-2026-V2 (Milestone M15.6).

Replaces prescriptive "Tract Sizing Advisor" with non-prescriptive descriptive profiles.
Features:
- Mini-PCNL (14–18 Fr) vs Standard PCNL (24–30 Fr) comparative trade-off analysis
- Caliber compatibility check against infundibular minimum Feret diameter
- Procedural trade-offs aligned directly with 2026 EAU Urolithiasis Guidelines
- Eliminates unsupported 1,500 / 2,500 mm³ hardcoded volume cutoffs
- Documents intrarenal pressure (IRP) as a contextual clinical consideration without false modeling claims
- Strict non-device CDS boundary: descriptive morphometrics, clinician-in-the-loop decision
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
import numpy as np

from acucalyx.endoscopy.skeletonizer import CollectingSystemGraph


class AccessCaliberClass(str, Enum):
    """Clinical access caliber category in percutaneous nephrolithotomy."""
    MINI_PCNL = "MINI_PCNL"          # 14–18 Fr access sheath
    STANDARD_PCNL = "STANDARD_PCNL"  # 24–30 Fr access sheath


@dataclass
class AccessCaliberProfile:
    """Descriptive mechanical and clinical characteristics of an access caliber tier."""
    caliber_class: AccessCaliberClass
    sheath_french: float
    sheath_outer_diameter_mm: float
    sheath_inner_diameter_mm: float
    infundibular_clearance_status: str  # "COMPATIBLE", "TIGHT_CLEARANCE", "INCOMPATIBLE"
    minimum_lumen_feret_required_mm: float
    actual_infundibulum_feret_min_mm: float
    primary_lithotripsy_modality: str
    evacuation_mechanism: str
    relative_operative_tradeoffs: Dict[str, str]
    clinical_governance_notice: str


@dataclass
class AccessCaliberComparisonReport:
    """Comprehensive comparative appraisal of compatible access-caliber profiles."""
    case_id: str
    candidate_id: str
    target_calyx_id: str
    total_stone_volume_mm3: float
    max_stone_caliper_mm: float
    target_calyx_min_feret_mm: float
    profiles: Dict[str, AccessCaliberProfile]
    descriptive_summary: str
    intrarenal_pressure_context: str
    governing_guideline_reference: str = "2026 EAU Guidelines on Urolithiasis (Percutaneous Nephrolithotomy)"


def generate_access_caliber_profiles(
    case_id: str,
    candidate_id: str,
    target_calyx_id: str,
    graph: CollectingSystemGraph,
    total_stone_volume_mm3: float,
    max_stone_caliper_mm: float,
) -> AccessCaliberComparisonReport:
    """
    Generates descriptive comparative access-caliber profiles for clinician review.
    
    Evaluates mechanical compatibility of 16 Fr (Mini-PCNL) and 28 Fr (Standard PCNL)
    sheaths against target infundibular caliber, highlighting procedural trade-offs
    per the 2026 EAU Urolithiasis guidelines without prescribing autonomous mandates.
    """
    target_calyx = graph.calyces.get(target_calyx_id)
    target_feret = target_calyx.infundibular_width_min_mm if target_calyx else 6.0

    # 1. Mini-PCNL Profile (Representative 16 Fr sheath: 5.33 mm OD, 4.8 mm ID)
    mini_od = 5.33
    mini_id = 4.80
    mini_req_feret = mini_od + 0.5  # 0.5 mm anatomical clearance margin
    if target_feret >= mini_req_feret:
        mini_status = "COMPATIBLE"
    elif target_feret >= mini_od:
        mini_status = "TIGHT_CLEARANCE"
    else:
        mini_status = "INCOMPATIBLE"

    mini_tradeoffs = {
        "bleeding_and_transfusion_risk": "Lower estimated blood loss and reduced transfusion requirement relative to standard tract (EAU 2026).",
        "hospital_stay": "Shorter post-procedural hospitalization reported across multiple randomized cohorts.",
        "evacuation_dynamics": "Relies on vacuum suction sheath (e.g. ClearPetra) or basket retrieval; direct stone grasping limited.",
        "operative_duration": "Operative time may be prolonged for large, complex, or staghorn stone burdens exceeding 20 mm in linear dimension.",
        "parenchymal_trauma": "Reduced parenchymal dilatation volume and lower risk of adjacent interlobar vessel shear injury.",
    }

    mini_profile = AccessCaliberProfile(
        caliber_class=AccessCaliberClass.MINI_PCNL,
        sheath_french=16.0,
        sheath_outer_diameter_mm=mini_od,
        sheath_inner_diameter_mm=mini_id,
        infundibular_clearance_status=mini_status,
        minimum_lumen_feret_required_mm=mini_req_feret,
        actual_infundibulum_feret_min_mm=target_feret,
        primary_lithotripsy_modality="Laser lithotripsy (High-power Holmium:YAG or Thulium Fiber Laser [TFL])",
        evacuation_mechanism="Vacuum suction sheath outflow or 1.8 Fr nitinol tipless retrieval basket",
        relative_operative_tradeoffs=mini_tradeoffs,
        clinical_governance_notice="Descriptive morphometric assessment. Does not constitute a clinical directive.",
    )

    # 2. Standard PCNL Profile (Representative 28 Fr sheath: 9.33 mm OD, 8.5 mm ID)
    std_od = 9.33
    std_id = 8.50
    std_req_feret = std_od + 0.5
    if target_feret >= std_req_feret:
        std_status = "COMPATIBLE"
    elif target_feret >= std_od:
        std_status = "TIGHT_CLEARANCE"
    else:
        std_status = "INCOMPATIBLE"

    std_tradeoffs = {
        "bleeding_and_transfusion_risk": "Higher potential bleeding rate and transfusion risk due to larger parenchymal tract caliber (EAU 2026).",
        "hospital_stay": "Standard post-procedural hospital observation; conventional nephrostomy or tubeless closure depending on patient status.",
        "evacuation_dynamics": "Direct ultrasonic or ballistic lithotrite with simultaneous high-volume aspiration; rapid fragment clearance.",
        "operative_duration": "Faster stone clearance rate for large staghorn or high-volume (>20 mm) calculus burdens.",
        "parenchymal_trauma": "Requires wider parenchymal tract dilatation; demands strict papillary entry to avoid interlobar vessels.",
    }

    std_profile = AccessCaliberProfile(
        caliber_class=AccessCaliberClass.STANDARD_PCNL,
        sheath_french=28.0,
        sheath_outer_diameter_mm=std_od,
        sheath_inner_diameter_mm=std_id,
        infundibular_clearance_status=std_status,
        minimum_lumen_feret_required_mm=std_req_feret,
        actual_infundibulum_feret_min_mm=target_feret,
        primary_lithotripsy_modality="Rigid ultrasonic lithotripsy, pneumatic/ballistic lithotrite, or high-power laser",
        evacuation_mechanism="High-flow continuous irrigation outflow and direct rigid three-prong or alligator grasping forceps",
        relative_operative_tradeoffs=std_tradeoffs,
        clinical_governance_notice="Descriptive morphometric assessment. Does not constitute a clinical directive.",
    )

    # Descriptive summary narrative
    descriptive_summary = (
        f"Case stone burden: {total_stone_volume_mm3:.1f} mm³ (maximum linear caliper: {max_stone_caliper_mm:.1f} mm). "
        f"Target calyx infundibular minimum Feret diameter: {target_feret:.1f} mm. "
        f"Mini-PCNL (16 Fr, OD {mini_od:.1f} mm) status: {mini_status}. "
        f"Standard PCNL (28 Fr, OD {std_od:.1f} mm) status: {std_status}. "
        f"Selection involves clinical balancing of clearance speed versus bleeding risk per operating surgeon judgment."
    )

    # Explicit scope note on intrarenal pressure
    irp_context = (
        "Clinical Context Notice on Intrarenal Pressure (IRP): The 2026 EAU guidelines emphasize that elevated sustained "
        "intrarenal pressure (>30–40 mmHg) during endourological procedures increases pyelovenous backflow and infectious risk. "
        "AcuCalyx reports geometric sheath and lumen caliber dimensions for clinician review; dynamic fluid pressures depend "
        "on intraoperative irrigation pump settings, sheath suction outflow, and operative duration and are not modeled computationally."
    )

    return AccessCaliberComparisonReport(
        case_id=case_id,
        candidate_id=candidate_id,
        target_calyx_id=target_calyx_id,
        total_stone_volume_mm3=total_stone_volume_mm3,
        max_stone_caliper_mm=max_stone_caliper_mm,
        target_calyx_min_feret_mm=target_feret,
        profiles={
            AccessCaliberClass.MINI_PCNL.value: mini_profile,
            AccessCaliberClass.STANDARD_PCNL.value: std_profile,
        },
        descriptive_summary=descriptive_summary,
        intrarenal_pressure_context=irp_context,
    )
