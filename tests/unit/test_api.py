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

