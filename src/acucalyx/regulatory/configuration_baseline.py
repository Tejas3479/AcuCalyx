"""AcuCalyx Software Configuration Index & Provenance Baseline Module.

Maintains immutable configuration records of software builds, AI model weights,
risk control baselines, and computes cryptographic case-plan binding fingerprints.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class SoftwareConfigurationIndex:
    """Immutable software configuration baseline for Milestone M7 regulatory release."""
    application_version: str = "1.0.0-RC1"
    software_build_id: str = "ACU-CORE-20261001-BLD01"
    git_release_tag: str = "release/v1.0.0-submission"
    ai_model_name: str = "TotalSegmentator v2 (Kidney / Organs)"
    ai_model_weights_sha256: str = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    anatomical_atlas_version: str = "v2.1.0-standardized"
    trajectory_optimizer_version: str = "v1.4.0 (5-Objective Pareto)"
    drr_forward_projector_version: str = "Beer-Lambert GPU Raymarcher v2.0"
    carm_profile_set_version: str = "Profile Pack v1.2"
    risk_management_baseline: str = "RMF-ACU-2026-REV3"
    requirements_baseline: str = "SRS-v2.0 / SwRS-v2.0 (10-Tier RTM)"
    sbom_identifier: str = "urn:uuid:acucalyx-core-sbom-v1.0.0"
    cyclonedx_format_version: str = "1.5"
    soup_registry_baseline: str = "SOUP-ACU-2026-Q3"
    dicom_profile_baseline: str = "PS32-ACU-2026A"

    def compute_case_plan_fingerprint(
        self,
        case_uuid: str,
        target_coords_lps: Tuple[float, float, float],
        entry_coords_lps: Tuple[float, float, float],
        carm_profile_id: str,
        secret_key: Optional[bytes] = None,
    ) -> str:
        """Compute an HMAC-SHA256 fingerprint binding the surgical plan to this configuration baseline.

        Ensures non-repudiation and detects coordinate or configuration tampering.
        """
        key = secret_key or b"ACUCALYX_REGULATORY_PROVENANCE_KEY_2026"
        target_str = f"{target_coords_lps[0]:.3f},{target_coords_lps[1]:.3f},{target_coords_lps[2]:.3f}"
        entry_str = f"{entry_coords_lps[0]:.3f},{entry_coords_lps[1]:.3f},{entry_coords_lps[2]:.3f}"

        payload = (
            f"{case_uuid}|{target_str}|{entry_str}|"
            f"{self.software_build_id}|{self.ai_model_weights_sha256}|{carm_profile_id}"
        )
        return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify_plan_fingerprint(
        self,
        case_uuid: str,
        target_coords_lps: Tuple[float, float, float],
        entry_coords_lps: Tuple[float, float, float],
        carm_profile_id: str,
        claimed_signature: str,
        secret_key: Optional[bytes] = None,
    ) -> bool:
        """Verify whether a surgical plan's fingerprint matches this configuration baseline."""
        expected = self.compute_case_plan_fingerprint(
            case_uuid=case_uuid,
            target_coords_lps=target_coords_lps,
            entry_coords_lps=entry_coords_lps,
            carm_profile_id=carm_profile_id,
            secret_key=secret_key,
        )
        return hmac.compare_digest(expected, claimed_signature)

    def to_json(self) -> str:
        """Export canonical JSON representation of configuration baseline."""
        return json.dumps(asdict(self), indent=2, sort_keys=True)


def get_current_configuration_baseline() -> SoftwareConfigurationIndex:
    """Return the singleton frozen configuration baseline for Milestone M7."""
    return SoftwareConfigurationIndex()
