"""
AcuCalyx Unit Tests: Formative Usability Protocol & Clinician Discovery Harness
(Milestone M14.5 / IEC 62366-1:2015)

Verifies:
1. Standard usability benchmark scenarios and tradeoff specifications.
2. Surgeon discovery interview guide protocol and markdown generation.
3. Usability study session lifecycle, trial recording, and comparative analytics.
4. REST API endpoints for scenarios, discovery guide, session start, trial capture, and report generation.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from acucalyx.research.human_factors.psychometrics import (
    NasaTlxRtlxAssessment,
    SystemUsabilityScaleAssessment,
)
from acucalyx.research.human_factors.usability_protocol import (
    ClinicianRole,
    STANDARD_USABILITY_SCENARIOS,
    SurgeonDiscoveryGuide,
    UsabilityCondition,
    UsabilityScenario,
    UsabilityStudySession,
    UsabilityTrialRecord,
)

client = TestClient(app)


def test_standard_usability_scenarios_completeness():
    """Verifies that all 4 clinical challenge scenarios are specified with clinical boundaries."""
    assert len(STANDARD_USABILITY_SCENARIOS) == 4
    for key in [
        "SCENARIO_01_LOWER_POLE",
        "SCENARIO_02_RETRORENAL_COLON",
        "SCENARIO_03_STAGHORN_INFUNDIBULUM",
        "SCENARIO_04_SUPRACOSTAL_HIGH_KIDNEY"
    ]:
        assert key in STANDARD_USABILITY_SCENARIOS
        sc = STANDARD_USABILITY_SCENARIOS[key]
        assert len(sc.title) > 5
        assert len(sc.clinical_summary) > 20
        assert sc.target_kidney_side in ("left", "right")
        assert len(sc.primary_tradeoffs) >= 1
        assert len(sc.benchmark_reference_tract) > 0
        assert len(sc.contraindicated_tracts) >= 1


def test_surgeon_discovery_guide_schema_and_markdown():
    """Verifies that the surgeon discovery interview protocol generates valid schema and markdown."""
    schema = SurgeonDiscoveryGuide.get_protocol_schema()
    assert schema["version"] == "1.0 (Milestone M14.5)"
    assert len(schema["sections"]) >= 4

    md = SurgeonDiscoveryGuide.generate_markdown_interview_sheet()
    assert "# AcuCalyx: Clinician Discovery & Tradeoff Weighting Interview" in md
    assert "Colon / Pleura Clearance" in md
    assert "Direct Forniceal / Papillary Access" in md
    assert "IEC 62366-1:2015" in md


def test_usability_study_session_comparative_analytics():
    """Verifies session telemetry aggregation, duration reductions, and paired workload analysis."""
    session = UsabilityStudySession(
        session_id="SESS_TEST_HF_01",
        investigator_id="Dr_Investigator"
    )

    # 2 baseline trials (conventional CT MPR)
    t_base_1 = UsabilityTrialRecord(
        trial_id="T_B1",
        session_id="SESS_TEST_HF_01",
        participant_id="SURGEON_01",
        participant_role=ClinicianRole.ATTENDING_ENDOUROLOGIST,
        experience_years=15,
        scenario_id="SCENARIO_01_LOWER_POLE",
        condition=UsabilityCondition.CONVENTIONAL_BASELINE,
        task_start_time="2026-10-14T10:00:00Z",
        task_end_time="2026-10-14T10:04:30Z",
        task_duration_seconds=270.0,
        selected_candidate_id="MANUAL_TRACT_01",
        selected_calyx_name="POSTERIOR_LOWER",
        accepted_automated_proposal=False,
        clinician_override_applied=False,
        critical_errors_observed=["C4_TRANSPOSITION_SUSPECTED"],
        nasa_tlx=NasaTlxRtlxAssessment(
            participant_id="SURGEON_01",
            condition_id="CONVENTIONAL_BASELINE",
            mental_demand=65.0,
            physical_demand=30.0,
            temporal_demand=55.0,
            performance=30.0,
            effort=60.0,
            frustration=40.0
        ),
        sus=None
    )

    t_base_2 = UsabilityTrialRecord(
        trial_id="T_B2",
        session_id="SESS_TEST_HF_01",
        participant_id="SURGEON_02",
        participant_role=ClinicianRole.ENDOUROLOGY_FELLOW,
        experience_years=3,
        scenario_id="SCENARIO_01_LOWER_POLE",
        condition=UsabilityCondition.CONVENTIONAL_BASELINE,
        task_start_time="2026-10-14T10:15:00Z",
        task_end_time="2026-10-14T10:20:00Z",
        task_duration_seconds=300.0,
        selected_candidate_id="MANUAL_TRACT_02",
        selected_calyx_name="POSTERIOR_LOWER",
        accepted_automated_proposal=False,
        clinician_override_applied=False,
        critical_errors_observed=[],
        nasa_tlx=NasaTlxRtlxAssessment(
            participant_id="SURGEON_02",
            condition_id="CONVENTIONAL_BASELINE",
            mental_demand=70.0,
            physical_demand=35.0,
            temporal_demand=60.0,
            performance=35.0,
            effort=65.0,
            frustration=45.0
        ),
        sus=None
    )

    # 2 AcuCalyx workbench trials
    t_acuc_1 = UsabilityTrialRecord(
        trial_id="T_A1",
        session_id="SESS_TEST_HF_01",
        participant_id="SURGEON_01",
        participant_role=ClinicianRole.ATTENDING_ENDOUROLOGIST,
        experience_years=15,
        scenario_id="SCENARIO_01_LOWER_POLE",
        condition=UsabilityCondition.ACUCALYX_WORKBENCH,
        task_start_time="2026-10-14T11:00:00Z",
        task_end_time="2026-10-14T11:01:45Z",
        task_duration_seconds=105.0,
        selected_candidate_id="CAND_01",
        selected_calyx_name="POSTERIOR_LOWER",
        accepted_automated_proposal=True,
        clinician_override_applied=False,
        critical_errors_observed=[],
        nasa_tlx=NasaTlxRtlxAssessment(
            participant_id="SURGEON_01",
            condition_id="ACUCALYX_WORKBENCH",
            mental_demand=25.0,
            physical_demand=15.0,
            temporal_demand=20.0,
            performance=10.0,
            effort=25.0,
            frustration=15.0
        ),
        sus=SystemUsabilityScaleAssessment(
            participant_id="SURGEON_01",
            item_responses=[5, 1, 5, 1, 5, 1, 5, 1, 5, 1]  # Score = 100
        )
    )

    t_acuc_2 = UsabilityTrialRecord(
        trial_id="T_A2",
        session_id="SESS_TEST_HF_01",
        participant_id="SURGEON_02",
        participant_role=ClinicianRole.ENDOUROLOGY_FELLOW,
        experience_years=3,
        scenario_id="SCENARIO_01_LOWER_POLE",
        condition=UsabilityCondition.ACUCALYX_WORKBENCH,
        task_start_time="2026-10-14T11:15:00Z",
        task_end_time="2026-10-14T11:17:00Z",
        task_duration_seconds=120.0,
        selected_candidate_id="CAND_01",
        selected_calyx_name="POSTERIOR_LOWER",
        accepted_automated_proposal=True,
        clinician_override_applied=False,
        critical_errors_observed=[],
        nasa_tlx=NasaTlxRtlxAssessment(
            participant_id="SURGEON_02",
            condition_id="ACUCALYX_WORKBENCH",
            mental_demand=30.0,
            physical_demand=20.0,
            temporal_demand=25.0,
            performance=15.0,
            effort=30.0,
            frustration=20.0
        ),
        sus=SystemUsabilityScaleAssessment(
            participant_id="SURGEON_02",
            item_responses=[4, 2, 4, 2, 4, 2, 4, 2, 4, 2]  # Score = 70
        )
    )

    session.record_trial(t_base_1)
    session.record_trial(t_base_2)
    session.record_trial(t_acuc_1)
    session.record_trial(t_acuc_2)

    summary = session.compute_summary_analytics()
    assert summary["total_trials"] == 4
    assert summary["baseline_trial_count"] == 2
    assert summary["acucalyx_trial_count"] == 2

    # Task duration reduction %
    mean_base = (270.0 + 300.0) / 2.0  # 285.0 s
    mean_acuc = (105.0 + 120.0) / 2.0  # 112.5 s
    expected_red = (285.0 - 112.5) / 285.0 * 100.0
    assert abs(summary["task_duration_seconds"]["reduction_percent"] - expected_red) < 0.2

    # Error elimination
    assert summary["critical_errors_observed"]["baseline_total"] == 1
    assert summary["critical_errors_observed"]["acucalyx_total"] == 0
    assert summary["critical_errors_observed"]["error_elimination_rate_pct"] == 100.0

    # Workload comparison
    assert summary["workload_analysis"] is not None
    assert summary["workload_analysis"]["mean_acucalyx_rtlx"] < summary["workload_analysis"]["mean_baseline_rtlx"]

    # SUS summary
    assert summary["sus_analysis"] is not None
    assert summary["sus_analysis"]["mean_sus"] == 87.5  # (100.0 + 75.0)/2


def test_api_usability_scenarios_and_interview_endpoints():
    """Verifies REST endpoints for scenarios and discovery guide."""
    # 1. Scenarios
    res_sc = client.get("/api/usability/scenarios")
    assert res_sc.status_code == 200
    scenarios = res_sc.json()
    assert len(scenarios) == 4
    assert any(s["scenario_id"] == "SCENARIO_02_RETRORENAL_COLON" for s in scenarios)

    # 2. Discovery guide schema
    res_guide = client.get("/api/usability/discovery/interview-guide")
    assert res_guide.status_code == 200
    guide_data = res_guide.json()
    assert "AcuCalyx Formative Surgeon Discovery" in guide_data["protocol_name"]

    # 3. Discovery guide markdown
    res_md = client.get("/api/usability/discovery/interview-guide/markdown")
    assert res_md.status_code == 200
    assert "# AcuCalyx: Clinician Discovery & Tradeoff Weighting Interview" in res_md.text


def test_api_usability_session_lifecycle_and_trial_recording():
    """Verifies end-to-end REST session lifecycle: start, submit trial, get report."""
    # 1. Start session
    start_res = client.post(
        "/api/usability/sessions/start",
        json={"investigator_id": "Dr_Test_Investigator"}
    )
    assert start_res.status_code == 200
    sess_data = start_res.json()
    session_id = sess_data["session_id"]
    assert sess_data["status"] == "INITIALIZED"

    # 2. Submit Baseline Trial
    t1_res = client.post(
        f"/api/usability/sessions/{session_id}/trials",
        json={
            "participant_id": "P_001",
            "participant_role": "ATTENDING_ENDOUROLOGIST",
            "experience_years": 12,
            "scenario_id": "SCENARIO_01_LOWER_POLE",
            "condition": "CONVENTIONAL_BASELINE",
            "task_start_time": "2026-10-14T12:00:00Z",
            "task_end_time": "2026-10-14T12:05:00Z",
            "task_duration_seconds": 300.0,
            "selected_candidate_id": "MANUAL_01",
            "selected_calyx_name": "POSTERIOR_LOWER",
            "accepted_automated_proposal": False,
            "clinician_override_applied": False,
            "nasa_tlx": {
                "mental_demand": 70.0,
                "physical_demand": 40.0,
                "temporal_demand": 60.0,
                "performance": 30.0,
                "effort": 65.0,
                "frustration": 50.0
            }
        }
    )
    assert t1_res.status_code == 200
    assert t1_res.json()["status"] == "RECORDED"

    # 3. Submit AcuCalyx Workbench Trial
    t2_res = client.post(
        f"/api/usability/sessions/{session_id}/trials",
        json={
            "participant_id": "P_001",
            "participant_role": "ATTENDING_ENDOUROLOGIST",
            "experience_years": 12,
            "scenario_id": "SCENARIO_01_LOWER_POLE",
            "condition": "ACUCALYX_WORKBENCH",
            "task_start_time": "2026-10-14T12:10:00Z",
            "task_end_time": "2026-10-14T12:12:00Z",
            "task_duration_seconds": 120.0,
            "selected_candidate_id": "CAND_POSTERIOR_LOWER",
            "selected_calyx_name": "POSTERIOR_LOWER",
            "accepted_automated_proposal": True,
            "clinician_override_applied": False,
            "nasa_tlx": {
                "mental_demand": 20.0,
                "physical_demand": 10.0,
                "temporal_demand": 15.0,
                "performance": 10.0,
                "effort": 20.0,
                "frustration": 10.0
            },
            "sus_responses": [5, 1, 5, 2, 5, 1, 5, 1, 5, 2]
        }
    )
    assert t2_res.status_code == 200
    assert t2_res.json()["trials_in_session"] == 2

    # 4. Fetch Formative Usability Report
    rep_res = client.get(f"/api/usability/sessions/{session_id}/report")
    assert rep_res.status_code == 200
    rep_data = rep_res.json()
    assert rep_data["total_trials"] == 2
    assert rep_data["baseline_trial_count"] == 1
    assert rep_data["acucalyx_trial_count"] == 1
    assert rep_data["task_duration_seconds"]["reduction_percent"] == 60.0  # (300 - 120)/300 = 60%
    assert rep_data["acceptance_metrics"]["acceptance_rate_pct"] == 100.0
    assert rep_data["sus_analysis"]["mean_sus"] > 80.0
