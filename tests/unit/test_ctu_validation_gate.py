"""
AcuCalyx Unit Tests: CT Urography Feasibility Pilot & M15-V Validation Gate
(Horizon 3 / Milestone M15.1 / IEC 62304 / ISO 14971)

Verifies:
1. REST API endpoint GET /api/validation/ctu/cohort returns full pilot cohort with consensus summaries.
2. Case-level endpoint GET /api/validation/ctu/cohort/{case_id} returns 3-reader annotations and pairwise Dice.
3. Execution endpoint POST /api/validation/ctu/benchmark/run runs VMTK reference centerline comparison
   and generates executive GO / NO-GO report.
4. Report endpoint GET /api/validation/ctu/benchmark/report caches and delivers the auditable report.
5. Ingestion endpoint POST /api/validation/ctu/ingest enforces fail-closed checks on non-opacified series.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_api_list_ctu_cohort():
    """Verifies that GET /api/validation/ctu/cohort lists the 4 pilot cases with consensus metadata."""
    res = client.get("/api/validation/ctu/cohort")
    assert res.status_code == 200
    cohort = res.json()
    assert len(cohort) >= 4

    case_ids = [c["case_id"] for c in cohort]
    assert "CTU_PILOT_01_LOWER_POLE" in case_ids
    assert "CTU_PILOT_04_NON_OPACIFIED_CONTROL" in case_ids

    # Verify opacification states
    c1 = next(c for c in cohort if c["case_id"] == "CTU_PILOT_01_LOWER_POLE")
    assert c1["opacification_quality"] == "ADEQUATE_EXCRETORY"
    assert c1["reader_count"] == 3
    assert c1["consensus_summary"] is not None
    assert c1["consensus_summary"]["mean_pairwise_dice"] > 0.80

    c4 = next(c for c in cohort if c["case_id"] == "CTU_PILOT_04_NON_OPACIFIED_CONTROL")
    assert c4["opacification_quality"] == "NON_OPACIFIED"


def test_api_get_ctu_case_details():
    """Verifies that GET /api/validation/ctu/cohort/{case_id} returns detailed reader annotations and consensus."""
    # 404 on nonexistent case
    res_404 = client.get("/api/validation/ctu/cohort/NONEXISTENT_CASE")
    assert res_404.status_code == 404

    # 200 on valid case
    res = client.get("/api/validation/ctu/cohort/CTU_PILOT_01_LOWER_POLE")
    assert res.status_code == 200
    data = res.json()
    assert data["case_id"] == "CTU_PILOT_01_LOWER_POLE"
    assert len(data["readers"]) == 3
    assert data["consensus"] is not None
    assert len(data["consensus"]["calyx_consensus"]) >= 3

    # Check that spatial dispersion is computed and bounded
    for c_name, c_metric in data["consensus"]["calyx_consensus"].items():
        assert c_metric["dispersion_radius_mm"] <= 5.0
        assert c_metric["is_high_disagreement"] is False


def test_api_run_and_get_m15_validation_benchmark():
    """Verifies that POST /api/validation/ctu/benchmark/run evaluates the cohort and produces GO_FEASIBILITY_PASSED."""
    run_res = client.post("/api/validation/ctu/benchmark/run?calyx_tolerance_mm=4.0&centerline_mae_threshold_mm=1.2")
    assert run_res.status_code == 200
    report = run_res.json()

    assert report["total_pilot_cases"] >= 4
    assert report["evaluable_cases"] >= 3
    assert report["rejected_non_opacified_cases"] >= 1
    assert report["mean_calyx_sensitivity"] >= 0.85
    assert report["mean_centerline_mae_mm"] <= 1.0
    assert report["all_cases_passed"] is True
    assert report["executive_decision"] == "GO_FEASIBILITY_PASSED"
    assert len(report["case_evaluations"]) >= 4

    # Check non-opacified rejection in case evaluations
    c4_eval = next(e for e in report["case_evaluations"] if e["case_id"] == "CTU_PILOT_04_NON_OPACIFIED_CONTROL")
    assert c4_eval["passed_case_criteria"] is False
    assert "REJECTED_NON_OPACIFIED" in c4_eval["rejection_reason"]

    # Verify GET /api/validation/ctu/benchmark/report returns the cached report
    rep_res = client.get("/api/validation/ctu/benchmark/report")
    assert rep_res.status_code == 200
    rep_data = rep_res.json()
    assert rep_data["report_id"] == report["report_id"]
    assert rep_data["executive_decision"] == "GO_FEASIBILITY_PASSED"


def test_api_ingest_ctu_case_with_opacification_check():
    """Verifies that POST /api/validation/ctu/ingest ingests valid cases and properly flags non-opacified scans."""
    # 1. Ingest valid excretory case
    ingest_payload = {
        "case_id": "CTU_PILOT_TEST_INGEST_01",
        "dicom_series_uid": "1.2.840.113619.2.55.999.1",
        "opacification_quality": "ADEQUATE_EXCRETORY",
        "grid_shape": [60, 60, 40],
        "spacing_mm": [1.0, 1.0, 1.0],
        "scanner_model": "GE Revolution CT",
        "contrast_agent": "Visipaque 320"
    }
    res = client.post("/api/validation/ctu/ingest", json=ingest_payload)
    assert res.status_code == 200
    assert res.json()["status"] == "INGESTED"
    assert res.json()["reader_count"] == 2

    # 2. Duplicate ID raises 409
    res_dup = client.post("/api/validation/ctu/ingest", json=ingest_payload)
    assert res_dup.status_code == 409

    # 3. Ingest non-opacified case -> status FLAGGED_NON_OPACIFIED
    non_op_payload = {
        "case_id": "CTU_PILOT_TEST_NON_OP",
        "dicom_series_uid": "1.2.840.113619.2.55.999.2",
        "opacification_quality": "NON_OPACIFIED",
        "grid_shape": [60, 60, 40],
        "spacing_mm": [1.0, 1.0, 1.0]
    }
    res_non_op = client.post("/api/validation/ctu/ingest", json=non_op_payload)
    assert res_non_op.status_code == 200
    assert res_non_op.json()["status"] == "FLAGGED_NON_OPACIFIED"
    assert res_non_op.json()["reader_count"] == 0
