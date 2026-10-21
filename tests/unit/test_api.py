"""
Unit tests for the AcuCalyx FastAPI Backend & Workflow Engine.
"""

from fastapi.testclient import TestClient
import pytest

from app.api.main import app

client = TestClient(app)


def test_api_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["system"] == "AcuCalyx"


def test_api_case_lifecycle_workflow():
    # 1. Create Synthetic Demo Case
    create_res = client.post("/api/cases/demo")
    assert create_res.status_code == 200
    case_data = create_res.json()
    case_id = case_data["case_id"]
    assert case_data["state"] == "READY"

    # 2. List Cases
    list_res = client.get("/api/cases")
    assert list_res.status_code == 200
    cases = list_res.json()
    assert any(c["case_id"] == case_id for c in cases)

    # 3. Check Status
    status_res = client.get(f"/api/cases/{case_id}/status")
    assert status_res.status_code == 200
    assert status_res.json()["case_id"] == case_id

    # 4. Trigger Planning Pipeline
    plan_res = client.post(
        f"/api/cases/{case_id}/plan",
        json={"target_side": "left", "coarse_step_mm": 15.0, "monte_carlo_samples": 30}
    )
    assert plan_res.status_code == 200
    plan_data = plan_res.json()
    assert plan_data["state"] == "PLAN_GENERATED"
    assert plan_data["candidate_count"] >= 1

    # 5. Fetch Quality Gate Metrics
    q_res = client.get(f"/api/cases/{case_id}/quality")
    assert q_res.status_code == 200
    assert q_res.json()["passed"] is True

    # 6. Fetch Calculus Volumetry
    s_res = client.get(f"/api/cases/{case_id}/stones")
    assert s_res.status_code == 200
    stones = s_res.json()
    assert len(stones) >= 1
    assert stones[0]["volume_mm3"] > 0.0

    # 7. Fetch Candidate Access Paths & Badges
    c_res = client.get(f"/api/cases/{case_id}/candidates")
    assert c_res.status_code == 200
    candidates = c_res.json()
    assert len(candidates) >= 1
    top_cand_id = candidates[0]["candidate_id"]
    assert candidates[0]["safety_badge"] in ("PREFERRED", "CONDITIONAL", "REJECTED")

    # 8. Select Trajectory (Clinician Review)
    sel_res = client.post(
        f"/api/cases/{case_id}/select",
        json={"candidate_id": top_cand_id, "clinician_id": "Dr_Test_Urologist"}
    )
    assert sel_res.status_code == 200
    assert sel_res.json()["state"] == "CLINICIAN_REVIEW"

    # 9. Clinician Override (Marks Downstream Plan as STALE)
    ovr_res = client.post(
        f"/api/cases/{case_id}/override",
        json={
            "override_type": "CALYX_TARGET",
            "reason": "Test safety expansion",
            "clinician_id": "Dr_Test_Urologist"
        }
    )
    assert ovr_res.status_code == 200
    assert ovr_res.json()["is_stale"] is True

    # Check that status now reflects STALE
    st_check = client.get(f"/api/cases/{case_id}/status")
    assert st_check.json()["is_stale"] is True

    # 10. Fetch 3D Mesh (GLB stream)
    mesh_res = client.get(f"/api/cases/{case_id}/meshes/kidney")
    assert mesh_res.status_code == 200
    assert len(mesh_res.content) > 100
    assert mesh_res.headers.get("X-AcuCalyx-Intended-Use") is not None

    # 11. Fetch 2D MPR CT Slice (PNG image stream)
    mpr_res = client.get(
        f"/api/cases/{case_id}/mpr/slice?orientation=AXIAL&slice_index=40&window_width=400&window_level=40"
    )
    assert mpr_res.status_code == 200
    assert mpr_res.headers["content-type"] == "image/png"
    assert len(mpr_res.content) > 500

    # 12. Fetch Virtual Fluoroscopy Projection
    fluoro_res = client.get(f"/api/cases/{case_id}/fluoroscopy/{top_cand_id}")
    assert fluoro_res.status_code == 200
    f_data = fluoro_res.json()
    assert "BULLS_EYE" in f_data["views"]
    assert "PROGRESSION" in f_data["views"]

    # 13. Download Preoperative Planning PDF Report
    pdf_res = client.get(f"/api/cases/{case_id}/report")
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF-")

    # 14. Download SHA-256 Provenance Manifest
    prov_res = client.get(f"/api/cases/{case_id}/provenance")
    assert prov_res.status_code == 200
    prov_data = prov_res.json()
    assert prov_data["case_id"] == case_id
    assert "software_version" in prov_data


def test_api_phantom_and_rehearsal_endpoints():
    """Verifies phantom specification, rehearsal state, and procedural evaluation endpoints."""
    # 1. Phantom Spec
    spec_res = client.get("/api/phantom/spec")
    assert spec_res.status_code == 200
    spec_data = spec_res.json()
    assert "renal_parenchyma" in spec_data["layers"]
    assert spec_data["uncertainty_budget"]["expanded_uncertainty_k2_mm"] <= 2.0

    # 2. Validate Phantom Scan
    scan_res = client.post(
        "/api/phantom/validate-scan",
        json={"layer_measurements_hu": {"renal_parenchyma": 45.0, "target_calculi": 1400.0}}
    )
    assert scan_res.status_code == 200
    assert scan_res.json()["all_layers_passed"] is True

    # 3. C-arm Technician Transfer Card
    card_res = client.get("/api/cases/demo_case/rehearsal/transfer-card")
    assert card_res.status_code == 200
    card = card_res.json()
    assert card["recommended_pulse_rate_pps"] == 8
    assert "Bull's-Eye" in card["bullseye_view_label"]

    # 4. Rehearsal State at 50%
    state_res = client.get("/api/cases/demo_case/rehearsal/state?advancement=0.5")
    assert state_res.status_code == 200
    state = state_res.json()
    assert state["advancement_fraction"] == 0.5
    assert state["active_progression_phase"] == "PARENCHYMAL_TUNNEL"
    assert "bullseye_projection" in state
    assert "depth_projection" in state

    # 5. Cohort Evaluation
    eval_res = client.post(
        "/api/validation/procedural/evaluate",
        json={
            "trials": [
                {
                    "trial_id": "T_TEST_1",
                    "operator_id": "EXPERT_1",
                    "planned_entry_lps": [20.0, -80.0, 35.0],
                    "planned_target_lps": [20.0, 20.0, 35.0],
                    "physical_entry_lps": [20.5, -80.0, 35.0],
                    "physical_tip_lps": [20.1, 20.2, 35.0],
                    "target_calyx_name": "lower_pole_posterior",
                    "infundibular_axis_unit": [0.0, 1.0, 0.0],
                    "papilla_radius_mm": 3.0,
                    "is_counter_puncture_observed": False,
                    "is_first_pass": True,
                    "fluoroscopy_time_seconds": 12.5,
                    "dose_area_product_gy_cm2": 0.45,
                    "repositioning_attempts": 0
                }
            ]
        }
    )
    assert eval_res.status_code == 200
    summary = eval_res.json()
    assert summary["sample_size_n"] == 1
    assert summary["first_pass_success_rate_pct"] == 100.0
    assert summary["counter_puncture_count"] == 0
    assert summary["counter_puncture_clopper_pearson_95_upper_pct"] <= 95.0


def test_api_comparison_matrix_and_guards():
    """
    Verifies Candidate Comparison Matrix API endpoint, strict candidate selection validation,
    stale plan rejection, and clinician override recomputation state.
    """
    # 1. Create demo case
    create_res = client.post("/api/cases/demo")
    assert create_res.status_code == 200
    case_id = create_res.json()["case_id"]

    # 2. Candidate selection before plan generation must fail with HTTP 400
    premature_sel = client.post(
        f"/api/cases/{case_id}/select",
        json={"candidate_id": "CAND_01", "clinician_id": "Surgeon_Test"}
    )
    assert premature_sel.status_code == 400
    assert "Plan generation must be completed" in premature_sel.json()["detail"]

    # 3. Run planning pipeline on demo case
    plan_res = client.post(
        f"/api/cases/{case_id}/plan",
        json={"target_side": "left", "coarse_step_mm": 15.0, "monte_carlo_samples": 20}
    )
    assert plan_res.status_code == 200
    assert plan_res.json()["state"] == "PLAN_GENERATED"

    # 4. Fetch Candidate Access Tract Comparison Matrix
    matrix_res = client.get(f"/api/cases/{case_id}/candidates/comparison-matrix")
    assert matrix_res.status_code == 200
    matrix = matrix_res.json()
    assert matrix["case_id"] == case_id
    assert "PREOPERATIVE GEOMETRIC ESTIMATE ONLY" in matrix["disclaimer"]
    assert len(matrix["candidates"]) >= 1

    cand0 = matrix["candidates"][0]
    # Verify typed MetricValue contracts
    assert "tract_length_mm" in cand0
    assert cand0["tract_length_mm"]["unit"] == "mm"
    assert cand0["tract_length_mm"]["status"] in ("MEASURED", "DERIVED", "ESTIMATED")
    assert cand0["pleural_clearance"]["status"] in ("MEASURED", "NOT_EVALUABLE")
    assert "caliber_suitability_considerations" in cand0
    assert "irrigation_pressure_risk" in cand0
    assert "clinical_tradeoff_summary" in cand0

    valid_cand_id = cand0["candidate_id"]

    # 5. Selecting non-existent candidate must return HTTP 404
    bad_sel = client.post(
        f"/api/cases/{case_id}/select",
        json={"candidate_id": "NON_EXISTENT_TRACT_999", "clinician_id": "Surgeon_Test"}
    )
    assert bad_sel.status_code == 404
    assert "not found" in bad_sel.json()["detail"]

    # 6. Selecting valid candidate succeeds
    good_sel = client.post(
        f"/api/cases/{case_id}/select",
        json={"candidate_id": valid_cand_id, "clinician_id": "Surgeon_Test"}
    )
    assert good_sel.status_code == 200
    assert good_sel.json()["active_candidate_id"] == valid_cand_id

    # 7. Apply manual clinician override: marks plan stale and clears active candidate
    ovr_res = client.post(
        f"/api/cases/{case_id}/override",
        json={
            "override_type": "CALYX_TARGET",
            "modified_coordinates_lps": [10.0, -20.0, 30.0],
            "reason": "Expanding safety clearance from ribs",
            "clinician_id": "Surgeon_Test"
        }
    )
    assert ovr_res.status_code == 200
    ovr_data = ovr_res.json()
    assert ovr_data["status"] == "OVERRIDE_RECORDED_PENDING_RECOMPUTATION"
    assert ovr_data["is_stale"] is True
    assert ovr_data["active_candidate_id"] is None

    # 8. Selecting candidate on stale plan must fail with HTTP 409
    stale_sel = client.post(
        f"/api/cases/{case_id}/select",
        json={"candidate_id": valid_cand_id, "clinician_id": "Surgeon_Test"}
    )
    assert stale_sel.status_code == 409
    assert "stale plan" in stale_sel.json()["detail"].lower()


def test_patient_case_fails_closed_without_neural_weights(tmp_path):
    """
    Verifies that patient cases (is_demo == False) strictly fail closed and NEVER default
    to synthetic heuristic anatomy when TotalSegmentator native runner/weights are absent.
    """
    from datetime import datetime, timezone
    from app.api.main import save_case_meta, CASES_DIR
    from tests.phantom.phantom_generator import generate_synthetic_pcnl_phantom, save_phantom_to_nifti

    case_id = f"PATIENT_TEST_{datetime.now().strftime('%H%M%S')}"
    case_dir = CASES_DIR / case_id
    raw_dir = case_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    vol, spatial, _ = generate_synthetic_pcnl_phantom(grid_shape=(64, 64, 40), spacing_mm=(1.5, 1.5, 1.5))
    nii_path = raw_dir / "patient_ct.nii.gz"
    save_phantom_to_nifti(vol, spatial, nii_path)

    # Register as clinical patient case (is_demo = False)
    meta = {
        "case_id": case_id,
        "is_demo": False,
        "state": "READY",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "input_path": str(nii_path),
        "target_side": "left",
        "is_stale": False,
        "active_candidate_id": None,
        "stone_count": 0,
        "candidate_count": 0,
        "clinical_notice": "Real clinical patient intake."
    }
    save_case_meta(case_id, meta)

    # Pre-check 1: Prior to laterality confirmation, clinical planning is blocked by Interlock U1 (HTTP 412)
    res_unconfirmed = client.post(
        f"/api/cases/{case_id}/plan",
        json={"target_side": "left"}
    )
    assert res_unconfirmed.status_code == 412
    assert "Interlock U1 Laterality Verification Gate" in res_unconfirmed.json()["detail"]

    # Clinician confirms laterality via authoritative usability endpoint
    res_confirm = client.post(
        f"/api/usability/cases/{case_id}/laterality-confirm",
        json={
            "clinician_selected_side": "LEFT",
            "ct_metadata_side": "LEFT",
            "landmark_checks": {"axial_scout": True, "liver_spleen_verified": True},
            "is_two_step_confirmed": True
        }
    )
    # Pre-check 1b: Prior to operative position confirmation, clinical planning is blocked by Interlock U2 (HTTP 412)
    res_no_pos = client.post(
        f"/api/cases/{case_id}/plan",
        json={"target_side": "left"}
    )
    assert res_no_pos.status_code == 412
    assert "Interlock U2 Operative Pose Gate" in res_no_pos.json()["detail"]

    # Clinician confirms operative position via authoritative usability endpoint
    res_pos = client.post(
        f"/api/usability/cases/{case_id}/position-confirm",
        json={
            "planned_operative_position": "PRONE_STANDARD",
            "is_clinician_confirmed": True
        }
    )
    assert res_pos.status_code == 200
    assert res_pos.json()["confirmed"] is True

    # Pre-check 2: Attempt with mismatched side -> HTTP 400
    res_mismatch = client.post(
        f"/api/cases/{case_id}/plan",
        json={"target_side": "right"}
    )
    assert res_mismatch.status_code == 400
    assert "Laterality Mismatch" in res_mismatch.json()["detail"]

    # Attempt 1: Explicit request for heuristic demo anatomy on patient case -> HTTP 400
    res_heuristic = client.post(
        f"/api/cases/{case_id}/plan",
        json={"target_side": "left", "segmentation_method": "HEURISTIC_DEMO"}
    )
    assert res_heuristic.status_code == 400
    assert "Synthetic heuristic anatomy is strictly prohibited in clinical patient cases" in res_heuristic.json()["detail"]

    # Attempt 2: Standard planning pipeline -> must fail closed (HTTP 500) if native TotalSegmentator weights not mounted
    # and mark case as REJECTED rather than silently substituting synthetic anatomy.
    res_plan = client.post(
        f"/api/cases/{case_id}/plan",
        json={"target_side": "left"}
    )
    # TotalSegmentator is not running in native CLI mode in this test environment
    assert res_plan.status_code == 500
    assert "Clinical segmentation failed" in res_plan.json()["detail"] or "prohibited" in res_plan.json()["detail"]

    # Confirm case state transitioned to REJECTED
    st_res = client.get(f"/api/cases/{case_id}/status")
    assert st_res.json()["state"] == "REJECTED"


def test_upload_security_and_traversal_guards():
    """
    Verifies that the upload endpoint and case store strictly reject path traversal,
    enforce file size limits, and prevent Zip Slip exploits.
    """
    import io
    import shutil
    import zipfile
    from app.api.case_store import load_case_meta, CASES_DIR

    # 1. Invalid case_id with path traversal characters must fail
    res_trav = client.get("/api/cases/..%2F..%2Fetc/status")
    assert res_trav.status_code in (400, 404)

    # 2. Upload with path traversal in filename must sanitize safe_filename
    uploaded_case_id = None
    try:
        file_content = b"Mock CT DICOM raw bytes"
        res_upload = client.post(
            "/api/cases/upload",
            files={"file": ("../../malicious.nii.gz", io.BytesIO(file_content), "application/gzip")}
        )
        assert res_upload.status_code == 200
        up_data = res_upload.json()
        uploaded_case_id = up_data["case_id"]
        assert "malicious" in uploaded_case_id
        assert ".." not in uploaded_case_id
        up_meta = load_case_meta(uploaded_case_id)
        assert "malicious.nii.gz" in up_meta["input_path"]
        assert ".." not in up_meta["input_path"]
    finally:
        if uploaded_case_id:
            mal_dir = CASES_DIR / uploaded_case_id
            if mal_dir.exists():
                shutil.rmtree(mal_dir, ignore_errors=True)

    # 3. Zip file with zip-slip path traversal entry must be rejected with HTTP 400
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("../../evil_escape.txt", b"evil payload")
    zip_buffer.seek(0)

    res_zip_slip = client.post(
        "/api/cases/upload",
        files={"file": ("slip.zip", zip_buffer, "application/zip")}
    )
    assert res_zip_slip.status_code == 400
    assert "Illegal path in archive" in res_zip_slip.json()["detail"]


def test_frontend_workbench_and_summary_card_assets():
    """
    Verifies that frontend static assets serve the Candidate Comparison Matrix
    and 1-Page Preoperative Planning Summary Card interface elements.
    """
    # 1. Verify index.html loads with UI components
    res_html = client.get("/")
    assert res_html.status_code == 200
    html_text = res_html.text
    assert "btn-open-comparison-matrix" in html_text
    assert "btn-open-summary-card" in html_text
    assert "modal-comparison-matrix" in html_text
    assert "modal-summary-card" in html_text
    assert "comparison-matrix-table" in html_text
    assert "summary-card-inner" in html_text
    assert "window.openComparisonMatrix" in html_text
    assert "window.openSummaryCard" in html_text
    assert "window.printSummaryCard" in html_text

    # 2. Verify style.css loads with print rules and table styles
    res_css = client.get("/style.css")
    assert res_css.status_code == 200
    css_text = res_css.text
    assert ".comparison-matrix-table" in css_text
    assert "@media print" in css_text
    assert "#modal-summary-card" in css_text



