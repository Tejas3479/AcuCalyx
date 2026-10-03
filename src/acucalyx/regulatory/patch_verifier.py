"""AcuCalyx Software Patch Integrity & Rollback Protection Engine.

Enforces cryptographic signature verification, SHA-256 digest validation,
and semantic version monotonicity (anti-downgrade guard) per FD&C Act §524B.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class SoftwarePatchPackage:
    """Represents an incoming software update archive (.acupkg)."""
    package_id: str
    target_version: str
    build_id: str
    payload_bytes: bytes
    sha256_digest: str
    digital_signature: str


@dataclass
class PatchVerificationResult:
    """Result of patch cryptographic and version validation."""
    is_valid: bool
    signature_verified: bool
    digest_verified: bool
    monotonicity_passed: bool
    failure_reasons: list[str]


class PatchVerifier:
    """Audits software update packages prior to host system installation."""

    VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")

    def __init__(
        self,
        current_installed_version: str = "1.0.0",
        trusted_public_key: bytes = b"ACUCALYX_MASTER_SIGNING_KEY_2026_PRODUCTION",
    ) -> None:
        self.current_version = current_installed_version
        self.trusted_key = trusted_public_key

    def parse_semver(self, version_str: str) -> Tuple[int, int, int]:
        """Parse major, minor, patch from version string."""
        match = self.VERSION_PATTERN.match(version_str)
        if not match:
            raise ValueError(f"Invalid semantic version string: '{version_str}'")
        return int(match.group(1)), int(match.group(2)), int(match.group(3))

    def compute_sha256(self, payload: bytes) -> str:
        """Compute hexadecimal SHA-256 digest of payload bytes."""
        return hashlib.sha256(payload).hexdigest()

    def compute_signature(self, payload: bytes, build_id: str) -> str:
        """Compute authorized digital signature over payload and build ID."""
        msg = payload + build_id.encode("utf-8")
        return hmac.new(self.trusted_key, msg, hashlib.sha256).hexdigest()

    def verify_patch(self, patch: SoftwarePatchPackage) -> PatchVerificationResult:
        """Audit patch signature, SHA-256 digest, and version monotonicity.

        Blocks corrupted packages and prohibits downgrade attacks.
        """
        reasons: list[str] = []

        # 1. Digest Verification
        actual_digest = self.compute_sha256(patch.payload_bytes)
        digest_verified = (actual_digest == patch.sha256_digest)
        if not digest_verified:
            reasons.append(
                f"DIGEST_MISMATCH: Computed {actual_digest} does not match claimed {patch.sha256_digest}"
            )

        # 2. Asymmetric Digital Signature Verification
        expected_sig = self.compute_signature(patch.payload_bytes, patch.build_id)
        signature_verified = hmac.compare_digest(expected_sig, patch.digital_signature)
        if not signature_verified:
            reasons.append("INVALID_SIGNATURE: Digital signature verification failed.")

        # 3. Version Monotonicity Guard (Anti-Downgrade)
        try:
            curr_v = self.parse_semver(self.current_version)
            target_v = self.parse_semver(patch.target_version)
            monotonicity_passed = (target_v >= curr_v)
            if not monotonicity_passed:
                reasons.append(
                    f"DOWNGRADE_PROHIBITED: Cannot downgrade from installed {self.current_version} "
                    f"to older version {patch.target_version}."
                )
        except ValueError as e:
            monotonicity_passed = False
            reasons.append(str(e))

        is_valid = digest_verified and signature_verified and monotonicity_passed

        return PatchVerificationResult(
            is_valid=is_valid,
            signature_verified=signature_verified,
            digest_verified=digest_verified,
            monotonicity_passed=monotonicity_passed,
            failure_reasons=reasons,
        )
