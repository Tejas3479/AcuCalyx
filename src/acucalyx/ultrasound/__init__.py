"""
AcuCalyx Ultrasound: Multimodal Ultrasound Simulation & Operative Positioning Uncertainty
Governed by ACU-M14-EXEC-PLAN-2026-V2.
"""

from acucalyx.ultrasound.reference_registry import (
    DualModalTissueProperty,
    DualModalPhantomSpecification,
    PairedUltrasoundCTCase,
    PCNLUltrasoundReferenceRegistry,
    STANDARD_DUAL_MODAL_PHANTOM_SPEC
)
from acucalyx.ultrasound.position_uncertainty import (
    OperativePosition,
    PatientHabitus,
    VentilationMode,
    StratifiedPositioningCovarianceEngine,
    PositionUncertaintyResult,
    evaluate_monte_carlo_hazard_clearance
)
from acucalyx.ultrasound.acoustic_properties import (
    TissueAcousticProperties,
    get_calibrated_tissue_acoustics,
    compute_two_way_attenuation_intensity
)
from acucalyx.ultrasound.probe_profile import (
    UltrasoundProbeProfile,
    CURVILINEAR_C5_2,
    LINEAR_L12_4,
    get_ultrasound_probe
)
from acucalyx.ultrasound.needle_ultrasound import (
    NeedleAcousticVisibilityResult,
    compute_needle_acoustic_visibility_index
)
from acucalyx.ultrasound.acoustic_window import (
    AcousticWindowStatus,
    AcousticWindowEvaluationResult,
    evaluate_flank_acoustic_window
)
from acucalyx.ultrasound.bmode_simulator import (
    SimulatedBModeImage,
    generate_simulated_bmode_ultrasound
)

__all__ = [
    "DualModalTissueProperty",
    "DualModalPhantomSpecification",
    "PairedUltrasoundCTCase",
    "PCNLUltrasoundReferenceRegistry",
    "STANDARD_DUAL_MODAL_PHANTOM_SPEC",
    "OperativePosition",
    "PatientHabitus",
    "VentilationMode",
    "StratifiedPositioningCovarianceEngine",
    "PositionUncertaintyResult",
    "evaluate_monte_carlo_hazard_clearance",
    "TissueAcousticProperties",
    "get_calibrated_tissue_acoustics",
    "compute_two_way_attenuation_intensity",
    "UltrasoundProbeProfile",
    "CURVILINEAR_C5_2",
    "LINEAR_L12_4",
    "get_ultrasound_probe",
    "NeedleAcousticVisibilityResult",
    "compute_needle_acoustic_visibility_index",
    "AcousticWindowStatus",
    "AcousticWindowEvaluationResult",
    "evaluate_flank_acoustic_window",
    "SimulatedBModeImage",
    "generate_simulated_bmode_ultrasound",
]
