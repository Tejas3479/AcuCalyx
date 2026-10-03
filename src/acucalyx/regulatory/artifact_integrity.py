"""AcuCalyx Artifact Integrity & Cryptographic Provenance Module.

Generates and audits SHA-256 cryptographic fingerprints across regulatory,
design history, and verification files to prevent tampering and ensure
reproducible submission baselines.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ArtifactFingerprint:
    """Immutable cryptographic record of a file artifact."""
    relative_path: str
    sha256_hash: str
    byte_size: int
    exists: bool


class ArtifactIntegrityAuditor:
    """Audits file integrity and cryptographic fingerprints against controlled baselines."""

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        self.workspace_root = workspace_root or Path.cwd()

    def compute_file_sha256(self, file_path: Path | str) -> str:
        """Compute hexadecimal SHA-256 digest of a target file."""
        target = Path(file_path)
        if not target.is_absolute():
            target = self.workspace_root / target
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"Target artifact does not exist: {target}")

        hasher = hashlib.sha256()
        with open(target, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def inspect_artifact(self, relative_path: str) -> ArtifactFingerprint:
        """Inspect a file relative to workspace root and generate its fingerprint."""
        target = self.workspace_root / relative_path
        if not target.exists() or not target.is_file():
            return ArtifactFingerprint(
                relative_path=relative_path,
                sha256_hash="",
                byte_size=0,
                exists=False,
            )
        file_hash = self.compute_file_sha256(target)
        size = target.stat().st_size
        return ArtifactFingerprint(
            relative_path=relative_path,
            sha256_hash=file_hash,
            byte_size=size,
            exists=True,
        )

    def audit_manifest(
        self, expected_manifest: Dict[str, str]
    ) -> Tuple[bool, List[str]]:
        """Audit a dictionary of {relative_path: expected_sha256}.

        Returns:
            Tuple of (all_passed: bool, failure_reasons: List[str])
        """
        all_passed = True
        failure_reasons: List[str] = []

        for rel_path, expected_hash in expected_manifest.items():
            fingerprint = self.inspect_artifact(rel_path)
            if not fingerprint.exists:
                all_passed = False
                failure_reasons.append(f"MISSING_ARTIFACT: {rel_path} does not exist on disk.")
                continue

            if expected_hash and fingerprint.sha256_hash != expected_hash:
                all_passed = False
                failure_reasons.append(
                    f"HASH_MISMATCH: {rel_path} actual hash {fingerprint.sha256_hash} "
                    f"does not match expected {expected_hash}."
                )

        return all_passed, failure_reasons
