"""AcuCalyx Cryptographic Plan Integrity & Canonical Fingerprint Engine.

Governed by FD&C Act §524B, FDA Premarket Cybersecurity Guidance (Feb 2026),
and ISO 13485:2016 Clause 7.3.
Ensures mathematical tamper detection and state validity for surgical plans.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class PlanState(str, Enum):
    """Lifecycle states of an AcuCalyx surgical plan."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    STALE = "STALE"
    SUPERSEDED = "SUPERSEDED"
    RECALCULATION_REQUIRED = "RECALCULATION_REQUIRED"
    TAMPERED_LOCK = "TAMPERED_LOCK"


@dataclass(frozen=True)
class PlanAuditEvent:
    """
    Tamper-evident audit event in an immutable hash chain.
    Records every lifecycle transition (PROPOSED, MODIFIED, SUPERSEDED, APPROVED).
    """
    event_id: str
    case_id: str
    plan_id: str
    previous_event_hash: str
    timestamp_utc: str
    actor_id: str
    action: str
    plan_payload_hash: str
    event_hash: str

    @classmethod
    def create(
        cls,
        case_id: str,
        plan_id: str,
        actor_id: str,
        action: str,
        plan_payload_hash: str,
        previous_event_hash: str = "GENESIS_0000000000000000000000000000000000000000000000000000000000000000",
        timestamp_utc: Optional[str] = None
    ) -> "PlanAuditEvent":
        import uuid
        from datetime import datetime, timezone
        ev_id = str(uuid.uuid4())
        ts = timestamp_utc or datetime.now(timezone.utc).isoformat()
        digest_input = f"{ev_id}|{case_id}|{plan_id}|{previous_event_hash}|{ts}|{actor_id}|{action}|{plan_payload_hash}"
        ev_hash = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
        return cls(
            event_id=ev_id,
            case_id=case_id,
            plan_id=plan_id,
            previous_event_hash=previous_event_hash,
            timestamp_utc=ts,
            actor_id=actor_id,
            action=action,
            plan_payload_hash=plan_payload_hash,
            event_hash=ev_hash
        )


class PlanTamperError(ValueError):
    """Raised when plan cryptographic fingerprint mismatches (PLAN_HASH_MISMATCH)."""
    pass


class PlanStaleError(RuntimeError):
    """Raised when attempting to execute or export a superseded stale plan."""
    pass


@dataclass
class CanonicalPlan:
    """Represents a frozen, cryptographically bound surgical PCNL access plan."""

    plan_id: str
    patient_id: str
    laterality: str  # "LEFT" or "RIGHT"
    target_point_lps: Tuple[float, float, float]
    entry_point_lps: Tuple[float, float, float]
    carm_bullseye_angles: Tuple[float, float]  # (LAO/RAO, CRA/CAU) in degrees
    carm_progression_angles: Tuple[float, float]  # (LAO/RAO, CRA/CAU) in degrees
    hazard_clearances_mm: Dict[str, float]
    maximum_depth_mm: float
    status: PlanState = PlanState.DRAFT
    timestamp_utc: str = "2026-09-30T12:00:00Z"
    approved_by: Optional[str] = None
    fingerprint: Optional[str] = None

    def to_canonical_dict(self) -> Dict[str, Any]:
        """Convert plan to deterministic, canonical dictionary with fixed float formatting."""
        return {
            "approved_by": self.approved_by,
            "carm_bullseye_angles": [round(float(a), 4) for a in self.carm_bullseye_angles],
            "carm_progression_angles": [round(float(a), 4) for a in self.carm_progression_angles],
            "entry_point_lps": [round(float(x), 4) for x in self.entry_point_lps],
            "hazard_clearances_mm": {k: round(float(v), 4) for k, v in sorted(self.hazard_clearances_mm.items())},
            "laterality": str(self.laterality).upper(),
            "maximum_depth_mm": round(float(self.maximum_depth_mm), 4),
            "patient_id": str(self.patient_id),
            "plan_id": str(self.plan_id),
            "status": self.status.value if isinstance(self.status, PlanState) else str(self.status),
            "target_point_lps": [round(float(x), 4) for x in self.target_point_lps],
            "timestamp_utc": str(self.timestamp_utc),
        }

    def serialize_canonical_json(self) -> str:
        """Deterministically serialize to JSON with sorted keys and no whitespace variation."""
        data = self.to_canonical_dict()
        return json.dumps(data, sort_keys=True, separators=(",", ":"))


class PlanIntegrityEngine:
    """Manages cryptographic hashing, signature binding, and tamper traps for plans."""

    @staticmethod
    def compute_fingerprint(plan: CanonicalPlan) -> str:
        """Compute SHA-256 fingerprint over canonical JSON bytes."""
        canonical_str = plan.serialize_canonical_json()
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    @classmethod
    def seal_plan(cls, plan: CanonicalPlan, approved_by: str) -> CanonicalPlan:
        """Seal an approved plan with a cryptographic fingerprint."""
        plan.status = PlanState.APPROVED
        plan.approved_by = approved_by
        plan.fingerprint = cls.compute_fingerprint(plan)
        return plan

    @classmethod
    def verify_plan(cls, plan: CanonicalPlan) -> bool:
        """Verify that the plan's fingerprint matches its current contents."""
        if plan.status == PlanState.STALE:
            raise PlanStaleError(f"Plan '{plan.plan_id}' is marked STALE and cannot be verified or used.")

        if not plan.fingerprint:
            raise PlanTamperError(f"Plan '{plan.plan_id}' has no cryptographic fingerprint attached.")

        computed = cls.compute_fingerprint(plan)
        if computed != plan.fingerprint:
            plan.status = PlanState.TAMPERED_LOCK
            raise PlanTamperError(
                f"PLAN_HASH_MISMATCH: Cryptographic fingerprint failed for plan '{plan.plan_id}'. "
                f"Expected {plan.fingerprint}, computed {computed}. Plan has been locked."
            )

        return True

    @classmethod
    def simulate_tampering_attack(
        cls, plan: CanonicalPlan, delta_entry_mm: Tuple[float, float, float]
    ) -> CanonicalPlan:
        """Simulate malicious in-transit alteration of entry coordinates."""
        tampered_entry = (
            plan.entry_point_lps[0] + delta_entry_mm[0],
            plan.entry_point_lps[1] + delta_entry_mm[1],
            plan.entry_point_lps[2] + delta_entry_mm[2],
        )
        plan.entry_point_lps = tampered_entry
        return plan

    @classmethod
    def supersede_plan(
        cls,
        prior_plan: CanonicalPlan,
        actor_id: str,
        reason: str,
        prior_audit_hash: str = "GENESIS_0000000000000000000000000000000000000000000000000000000000000000"
    ) -> Tuple[CanonicalPlan, PlanAuditEvent]:
        """
        Marks an existing plan as SUPERSEDED (Interlock U6) and emits a tamper-evident audit record.
        Preserves complete historical audit trail rather than mutating/deleting prior plans.
        """
        prior_plan.status = PlanState.SUPERSEDED
        payload_hash = cls.compute_fingerprint(prior_plan)
        audit_event = PlanAuditEvent.create(
            case_id=prior_plan.patient_id,
            plan_id=prior_plan.plan_id,
            actor_id=actor_id,
            action=f"SUPERSEDED: {reason}",
            plan_payload_hash=payload_hash,
            previous_event_hash=prior_audit_hash
        )
        return prior_plan, audit_event
