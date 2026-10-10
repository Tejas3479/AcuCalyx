"""
AcuCalyx Endoscopy Package
Milestone M15: Device-Specific Endoscopic Reachability, Kinematic Workspace & Computed Endoluminal Rehearsal
Governed by ACU-M15-EXEC-PLAN-2026-V2.
"""

from acucalyx.endoscopy.instrument_registry import (
    EndoscopeClass,
    WorkingChannelTool,
    ValidatedEndoscopeProfile,
    PhysicalPhantomSpecification,
    get_endoscope_profile,
    list_all_endoscopes,
    get_active_deflection,
    STANDARD_ENDOSCOPES,
    M15_REFERENCE_PHANTOMS,
)
from acucalyx.endoscopy.skeletonizer import (
    CenterlineNode,
    CrossSectionalGeometry,
    CenterlineEdge,
    CalyxMorphometry,
    CollectingSystemGraph,
    build_procedural_collecting_system_graph,
)
from acucalyx.endoscopy.reachability_engine import (
    ReachabilityStatus,
    CalyxReachabilityResult,
    TrajectoryReachabilityReport,
    evaluate_rigid_corridor_reachability,
    evaluate_flexible_kinematic_reachability,
    evaluate_trajectory_reachability,
)
from acucalyx.endoscopy.stone_coverage import (
    StoneAccessClass,
    StoneBurdenUnit,
    StoneCoverageItem,
    StoneAccessCoverageMap,
    evaluate_geometric_stone_coverage,
)
from acucalyx.endoscopy.tract_sizing import (
    AccessCaliberClass,
    AccessCaliberProfile,
    AccessCaliberComparisonReport,
    generate_access_caliber_profiles,
)
from acucalyx.endoscopy.virtual_nephroscopy import (
    EndoluminalKeyframe,
    ComputedEndoluminalRehearsalTrajectory,
    generate_endoluminal_rehearsal_trajectory,
)
from acucalyx.endoscopy.reachability_validator import (
    MorphometryValidationResult,
    ReachabilityClassificationMetrics,
    InterRaterReliabilityResult,
    PhysicalPhantomConcordanceResult,
    M15ValidationGateReport,
    evaluate_m15_validation_gate,
)

__all__ = [
    "EndoscopeClass",
    "WorkingChannelTool",
    "ValidatedEndoscopeProfile",
    "PhysicalPhantomSpecification",
    "get_endoscope_profile",
    "list_all_endoscopes",
    "get_active_deflection",
    "STANDARD_ENDOSCOPES",
    "M15_REFERENCE_PHANTOMS",
    "CenterlineNode",
    "CrossSectionalGeometry",
    "CenterlineEdge",
    "CalyxMorphometry",
    "CollectingSystemGraph",
    "build_procedural_collecting_system_graph",
    "ReachabilityStatus",
    "CalyxReachabilityResult",
    "TrajectoryReachabilityReport",
    "evaluate_rigid_corridor_reachability",
    "evaluate_flexible_kinematic_reachability",
    "evaluate_trajectory_reachability",
    "StoneAccessClass",
    "StoneBurdenUnit",
    "StoneCoverageItem",
    "StoneAccessCoverageMap",
    "evaluate_geometric_stone_coverage",
    "AccessCaliberClass",
    "AccessCaliberProfile",
    "AccessCaliberComparisonReport",
    "generate_access_caliber_profiles",
    "EndoluminalKeyframe",
    "ComputedEndoluminalRehearsalTrajectory",
    "generate_endoluminal_rehearsal_trajectory",
    "MorphometryValidationResult",
    "ReachabilityClassificationMetrics",
    "InterRaterReliabilityResult",
    "PhysicalPhantomConcordanceResult",
    "M15ValidationGateReport",
    "evaluate_m15_validation_gate",
]
