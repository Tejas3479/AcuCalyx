"""AcuCalyx IEC 62304 Clause 5.3 Safety Boundary & Architectural Partitioning Controller.

Enforces strict isolation between Safety-Relevant Computational Core (Class C),
Safety-Related Presentation & Interlocks (Class B/C), and Non-Safety UI (Class A).
Prevents non-safety components from compromising safety-critical state.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Set


class SoftwareSafetyClass(str, Enum):
    """IEC 62304 Software Safety Classifications."""

    CLASS_A = "CLASS_A"  # No injury or damage to health possible
    CLASS_B = "CLASS_B"  # Non-serious injury possible
    CLASS_C = "CLASS_C"  # Death or serious injury possible


class SafetyPartition(str, Enum):
    """Architectural partitions of the AcuCalyx software system."""

    SAFETY_CORE = "SAFETY_CORE"  # Computational kernel (Class C)
    SAFETY_PRESENTATION = "SAFETY_PRESENTATION"  # Safety interlocks & warnings (Class B/C)
    NON_SAFETY_UI = "NON_SAFETY_UI"  # WebGL/Three.js camera controls & cosmetics (Class A)


class DataContractViolationError(PermissionError):
    """Raised when a lower-criticality partition attempts unauthorized write or mutation."""
    pass


class SafetyBoundaryController:
    """Enforces architectural safety partitioning and one-way data contracts."""

    # Allowed mutation paths: A partition can mutate itself or call downstream safely
    _ALLOWED_MUTATIONS = {
        SafetyPartition.SAFETY_CORE: {SafetyPartition.SAFETY_CORE, SafetyPartition.SAFETY_PRESENTATION},
        SafetyPartition.SAFETY_PRESENTATION: {SafetyPartition.SAFETY_PRESENTATION},
        SafetyPartition.NON_SAFETY_UI: {SafetyPartition.NON_SAFETY_UI},
    }

    def __init__(self) -> None:
        self.audit_log: List[Dict[str, Any]] = []

    def validate_mutation_permission(
        self,
        source: SafetyPartition,
        target: SafetyPartition,
        operation: str = "MUTATE_STATE",
    ) -> bool:
        """Validate whether the source partition is permitted to mutate target partition state.

        Non-Safety UI (Class A) is NEVER permitted to mutate Safety Core (Class C).
        """
        allowed = target in self._ALLOWED_MUTATIONS.get(source, set())

        record = {
            "source": source.value,
            "target": target.value,
            "operation": operation,
            "permitted": allowed,
        }
        self.audit_log.append(record)

        if not allowed:
            raise DataContractViolationError(
                f"SAFETY BOUNDARY VIOLATION: Partition '{source.value}' is not permitted to mutate "
                f"state in '{target.value}'. Operation '{operation}' was rejected to preserve Class C integrity."
            )

        return True

    def sanitize_ui_payload(self, raw_ui_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Strip any safety-critical trajectory or hazard overrides from non-safety UI payloads."""
        forbidden_keys = {
            "target_point_lps",
            "entry_point_lps",
            "hazard_clearances_mm",
            "maximum_depth_mm",
            "laterality",
            "fingerprint",
            "status",
        }

        sanitized = {k: v for k, v in raw_ui_dict.items() if k not in forbidden_keys}
        return sanitized

    def enforce_fail_closed_contract(
        self,
        calculation_successful: bool,
        error_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Enforce fail-closed invariant: on calculation error, return 'No Plan' and lock output."""
        if not calculation_successful:
            return {
                "status": "FAIL_CLOSED_NO_PLAN",
                "feasible": False,
                "trajectories": [],
                "error_code": error_code or "ERR_CALCULATION_INDETERMINATE",
                "rehearsal_permitted": False,
                "message": "AcuCalyx Safety Kernel: No safe trajectory satisfies visceral clearance constraints.",
            }

        return {
            "status": "FEASIBLE_PLAN_PRODUCED",
            "feasible": True,
            "rehearsal_permitted": True,
        }
