"""
Unit tests for AcuCalyx case provenance and reproducibility tracking.
"""

from acucalyx.audit.provenance import create_provenance_record, compute_sha256_bytes


def test_provenance_record_reproducibility():
    """Verify provenance record produces deterministic SHA-256 hash for identical config."""
    cfg = {"threshold_hu": 400.0, "sigma_mm": 1.5, "mode": "STANDARD_NCCT"}
    rec1 = create_provenance_record(
        case_id="CASE_001",
        study_uid="1.2.840.10008.1",
        series_uid="1.2.840.10008.2",
        config_dict=cfg
    )
    rec2 = create_provenance_record(
        case_id="CASE_001",
        study_uid="1.2.840.10008.1",
        series_uid="1.2.840.10008.2",
        config_dict=cfg
    )

    assert rec1.configuration_sha256 == rec2.configuration_sha256
    assert rec1.case_id == "CASE_001"
    assert rec1.software_version == "0.2.0"
