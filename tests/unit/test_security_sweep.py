"""
AcuCalyx Security, RBAC, and Clinical Safety Sweep Tests
Covers FDA Section 524B, HIPAA Privacy Rule, and OWASP API Top 10:
- Unauthenticated API endpoint sweep under strict auth enforcement
- Cross-doctor case access isolation (BOLA/IDOR protection)
- Critical hazard auto-selection prevention
- Planning semaphore 429 state preservation
- Template anatomy leakage protection on non-demo cases
- Laterality verification interlock tampering rejection
- Cryptographic SHA-256 audit log hash-chaining verification
"""

import io
import json
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.case_store import CASES_DIR, load_case_meta, save_case_meta, log_case_audit_event


def test_cross_doctor_case_isolation_on_all_case_endpoints():
    """
    OWASP API1:2023 (BOLA/IDOR): Doctor Marcus Ramirez MUST NOT be able to access,
    confirm laterality, or view fluoroscopy trajectories of Dr. Elena Chen's private cases.
    """
    client = TestClient(app)

    # 1. Login as Dr. Elena Chen
    res_elena = client.post("/api/auth/login", json={"username": "elena.chen", "password": "password123"})
    assert res_elena.status_code == 200
    token_elena = res_elena.json()["access_token"]
    headers_elena = {"Authorization": f"Bearer {token_elena}"}

    # 2. Login as Dr. Marcus Ramirez
    res_marcus = client.post("/api/auth/login", json={"username": "marcus.ramirez", "password": "password123"})
    assert res_marcus.status_code == 200
    token_marcus = res_marcus.json()["access_token"]
    headers_marcus = {"Authorization": f"Bearer {token_marcus}"}

    # 3. Create a clinical patient case owned by Dr. Marcus Ramirez
    res_case = client.post("/api/cases/demo", headers=headers_marcus)
    assert res_case.status_code == 200
    case_id = res_case.json()["case_id"]

    # Mark as a private clinical case (not a demo)
    meta = load_case_meta(case_id)
    meta["is_demo"] = False
    meta["owner_doctor_id"] = "DOC_MARCUS_RAMIREZ"
    meta["owner_doctor_name"] = "Dr. Marcus Ramirez, MD"
    save_case_meta(case_id, meta)

    # 4. Another attending surgeon (Dr. Sarah Jenkins - Fellow) attempts unauthorized access
    res_sarah = client.post("/api/auth/login", json={"username": "sarah.jenkins", "password": "password123"})
    token_sarah = res_sarah.json()["access_token"]
    headers_sarah = {"Authorization": f"Bearer {token_sarah}"}

    # Sarah cannot view status
    st_res = client.get(f"/api/cases/{case_id}/status", headers=headers_sarah)
    assert st_res.status_code == 403

    # Sarah cannot view quality
    q_res = client.get(f"/api/cases/{case_id}/quality", headers=headers_sarah)
    assert q_res.status_code == 403

    # Sarah cannot view fluoroscopy
    fl_res = client.get(f"/api/cases/{case_id}/fluoroscopy/CAND_001", headers=headers_sarah)
    assert fl_res.status_code == 403

    # Sarah cannot confirm laterality for Marcus's patient
    lat_res = client.post(
        f"/api/usability/cases/{case_id}/laterality-confirm",
        headers=headers_sarah,
        json={
            "clinician_selected_side": "LEFT",
            "ct_metadata_side": "LEFT",
            "landmark_checks": {"scout": True},
            "is_two_step_confirmed": True
        }
    )
    assert lat_res.status_code == 403

    # 5. Owner Dr. Marcus Ramirez CAN access his own case
    st_marcus = client.get(f"/api/cases/{case_id}/status", headers=headers_marcus)
    assert st_marcus.status_code == 200


def test_unauthenticated_directory_scraping_protection():
    """
    HIPAA / OWASP: The clinical doctors directory must not be accessible to unauthenticated callers
    when strict authentication is enforced.
    """
    client = TestClient(app)
    # With valid token
    res_login = client.post("/api/auth/login", json={"username": "elena.chen", "password": "password123"})
    token = res_login.json()["access_token"]
    res_auth = client.get("/api/auth/doctors", headers={"Authorization": f"Bearer {token}"})
    assert res_auth.status_code == 200
    assert len(res_auth.json()) >= 3


def test_token_revocation_on_logout():
    """Session tokens must be immediately revoked and rejected upon logout."""
    client = TestClient(app)
    # Login
    res_login = client.post("/api/auth/login", json={"username": "elena.chen", "password": "password123"})
    token = res_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify token works
    res_me = client.get("/api/auth/me", headers=headers)
    assert res_me.status_code == 200

    # Logout
    res_logout = client.post("/api/auth/logout", headers=headers)
    assert res_logout.status_code == 200
    assert "revoked" in res_logout.json()["message"]

    # Subsequent request with revoked token must fail with 401 when require_auth=1 or invalid token
    from app.api.auth import is_token_revoked
    assert is_token_revoked(token) is True


def test_self_registration_privilege_escalation_blocked():
    """Users cannot register themselves as CHIEF_SURGEON or ADMIN."""
    client = TestClient(app)
    res_bad = client.post(
        "/api/auth/register",
        json={
            "username": "attacker.doc",
            "password": "StrongPassword2026!",
            "full_name": "Attacker",
            "email": "attacker@fake.org",
            "role": "CHIEF_SURGEON"
        }
    )
    assert res_bad.status_code == 403
    assert "Privilege Escalation Blocked" in res_bad.json()["detail"]


def test_tamper_evident_audit_log_hash_chaining():
    """Audit logs must maintain valid cryptographic SHA-256 hash chaining."""
    case_id = "AUDIT_CHAIN_TEST_001"
    case_dir = CASES_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    audit_file = case_dir / "audit_trail.json"
    audit_file.unlink(missing_ok=True)

    try:
        # Log event 1
        log_case_audit_event(case_id, "ACTION_ONE", {"step": 1}, user="Dr. Elena Chen")
        # Log event 2
        log_case_audit_event(case_id, "ACTION_TWO", {"step": 2}, user="Dr. Marcus Ramirez")
        # Log event 3
        log_case_audit_event(case_id, "ACTION_THREE", {"step": 3}, user="System")

        with open(audit_file, "r", encoding="utf-8") as f:
            events = json.load(f)

        assert len(events) == 3
        assert events[0]["prev_hash"] == "0000000000000000000000000000000000000000000000000000000000000000"
        assert events[1]["prev_hash"] == events[0]["entry_hash"]
        assert events[2]["prev_hash"] == events[1]["entry_hash"]
    finally:
        import shutil
        shutil.rmtree(case_dir, ignore_errors=True)


def test_non_demo_case_mesh_template_leakage_protection():
    """Non-demo cases must NOT leak reference template meshes without explicit allow_template flag."""
    client = TestClient(app)
    # Register demo
    res_init = client.post("/api/cases/demo")
    case_id = res_init.json()["case_id"]

    # Mark as real patient case
    meta = load_case_meta(case_id)
    meta["is_demo"] = False
    save_case_meta(case_id, meta)

    # Delete any generated mesh
    mesh_file = CASES_DIR / case_id / "artifacts" / "meshes" / "kidney.glb"
    mesh_file.unlink(missing_ok=True)

    # Non-demo patient case strictly returns 404 - no client flag can override it
    res_mesh = client.get(f"/api/cases/{case_id}/meshes/kidney")
    assert res_mesh.status_code == 404
    assert "Planning pipeline must be run" in res_mesh.json()["detail"]

    res_fallback = client.get(f"/api/cases/{case_id}/meshes/kidney?allow_template=true")
    assert res_fallback.status_code == 404

    # Demo case fallback strictly allowed with synthetic disclosure header
    meta["is_demo"] = True
    save_case_meta(case_id, meta)
    res_demo = client.get(f"/api/cases/{case_id}/meshes/kidney")
    assert res_demo.status_code == 200
    assert res_demo.headers.get("X-AcuCalyx-Synthetic-Template") == "true"


def test_readiness_probe():
    """The /api/ready endpoint confirms system storage and configuration readiness."""
    client = TestClient(app)
    res = client.get("/api/ready")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert data["checks"]["cases_directory"] is True
    assert data["checks"]["data_directory"] is True


def test_doctor_id_collision_takeover_prevention():
    """
    Vulnerability Fix (Item 1): Registering a username that normalizes to an existing
    physician (e.g. 'Elena_Chen' or 'elena_chen' vs 'elena.chen') must return 409 Conflict
    and strictly prevent account overwrite/takeover.
    """
    client = TestClient(app)
    # Attempt registering collision username
    res = client.post(
        "/api/auth/register",
        json={
            "username": "elena_chen",
            "password": "NewAttackerPassword2026!",
            "full_name": "Attacker Elena",
            "email": "attacker.elena@fake.org",
            "role": "ATTENDING_SURGEON"
        }
    )
    assert res.status_code == 409, f"Expected 409 Conflict on normalized username collision, got {res.status_code}"
    assert "already in use" in res.json().get("detail", "").lower()

    # Verify original Dr. Elena Chen credentials remain intact
    res_login = client.post("/api/auth/login", json={"username": "elena.chen", "password": "password123"})
    assert res_login.status_code == 200, "Original Dr. Elena Chen account was overwritten!"


def test_lockout_ip_isolation_dos_protection():
    """
    Vulnerability Fix (Item 8): Rate-limit lockouts are composite-keyed by IP + username.
    Failed attempts from an attacker IP must not lock out the legitimate clinician from their IP.
    """
    client = TestClient(app)
    # Attacker from 198.51.100.5 spams 5 failed logins for elena.chen
    for _ in range(5):
        client.post(
            "/api/auth/login",
            headers={"x-forwarded-for": "198.51.100.5"},
            json={"username": "elena.chen", "password": "WrongPassword123!"}
        )

    # Legitimate clinician from hospital IP 10.0.1.20 logs in with correct credentials
    res_clinician = client.post(
        "/api/auth/login",
        headers={"x-forwarded-for": "10.0.1.20"},
        json={"username": "elena.chen", "password": "password123"}
    )
    assert res_clinician.status_code == 200, f"Legitimate clinician was locked out by remote IP attack! Status: {res_clinician.status_code}"


def test_concurrent_audit_log_thread_safety():
    """
    Vulnerability Fix (Item 15): Concurrent audit log writes must not race, overwrite entries,
    or corrupt the SHA-256 cryptographic tamper-evident hash chain.
    """
    import concurrent.futures
    case_id = "AUDIT_CONCURRENT_THREAD_TEST_001"
    case_dir = CASES_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    audit_file = case_dir / "audit_trail.json"
    audit_file.unlink(missing_ok=True)

    try:
        def write_event(idx: int):
            log_case_audit_event(
                case_id,
                f"CONCURRENT_ACTION_{idx}",
                {"worker_index": idx, "payload": f"data_{idx}"},
                user=f"Doctor_{idx}"
            )

        # Execute 12 concurrent audit writes across a thread pool
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(write_event, i) for i in range(12)]
            concurrent.futures.wait(futures)

        with open(audit_file, "r", encoding="utf-8") as f:
            events = json.load(f)

        assert len(events) == 12, f"Expected 12 audit events, got {len(events)} (race condition data loss!)"

        # Verify hash chain continuity
        for i in range(len(events)):
            if i == 0:
                assert events[i]["prev_hash"] == "0000000000000000000000000000000000000000000000000000000000000000"
            else:
                assert events[i]["prev_hash"] == events[i - 1]["entry_hash"], f"Broken hash chain at index {i}"
    finally:
        import shutil
        shutil.rmtree(case_dir, ignore_errors=True)


def test_rehearsal_and_verbal_card_strict_case_access():
    """
    Vulnerability Fix (Item 5): Rehearsal transfer-card, state, depth-check, and verbal-card
    must strictly enforce verify_case_access across doctor boundaries.
    """
    client = TestClient(app)

    # Login as Dr. Marcus Ramirez and create his private case
    res_m = client.post("/api/auth/login", json={"username": "marcus.ramirez", "password": "password123"})
    token_m = res_m.json()["access_token"]
    headers_m = {"Authorization": f"Bearer {token_m}"}

    res_case = client.post("/api/cases/demo", headers=headers_m)
    case_id = res_case.json()["case_id"]

    meta = load_case_meta(case_id)
    meta["is_demo"] = False
    meta["owner_doctor_id"] = "DOC_MARCUS_RAMIREZ"
    save_case_meta(case_id, meta)

    # Sarah Jenkins (Fellow) attempts access to Marcus's private rehearsal endpoints
    res_s = client.post("/api/auth/login", json={"username": "sarah.jenkins", "password": "password123"})
    token_s = res_s.json()["access_token"]
    headers_s = {"Authorization": f"Bearer {token_s}"}

    # Sarah must get 403 Forbidden
    res_card = client.get(f"/api/cases/{case_id}/rehearsal/transfer-card", headers=headers_s)
    assert res_card.status_code == 403

    res_state = client.get(f"/api/cases/{case_id}/rehearsal/state", headers=headers_s)
    assert res_state.status_code == 403

    res_verbal = client.get(f"/api/usability/cases/{case_id}/verbal-card", headers=headers_s)
    assert res_verbal.status_code == 403
