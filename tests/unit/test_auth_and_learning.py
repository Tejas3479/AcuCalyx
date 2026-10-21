"""
Unit Tests for AcuCalyx Doctor Authentication, Patient Privacy Isolation,
and Privacy-Preserving Federated Learning / Differential Privacy.
"""

import pytest
from fastapi.testclient import TestClient
from app.api.main import app
from app.api.auth import hash_password, verify_password, create_access_token, verify_access_token
from src.acucalyx.ai.federated_learning import TrajectoryScoringModel, DifferentialPrivacyEngine, DifferentialPrivacyConfig
import numpy as np

client = TestClient(app)


def test_password_hashing_and_tokens():
    salt, pwd_hash = hash_password("SecretSurgeon2026!")
    assert verify_password("SecretSurgeon2026!", salt, pwd_hash) is True
    assert verify_password("WrongPassword!", salt, pwd_hash) is False

    token = create_access_token("DOC_TEST", "dr.test", "ATTENDING_SURGEON")
    payload = verify_access_token(token)
    assert payload is not None
    assert payload["sub"] == "DOC_TEST"
    assert payload["usr"] == "dr.test"


def test_doctor_login_endpoint():
    res = client.post("/api/auth/login", json={"username": "elena.chen", "password": "password123"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["doctor"]["username"] == "elena.chen"
    assert data["doctor"]["role"] == "CHIEF_SURGEON"


def test_doctor_patient_privacy_isolation():
    # Login as Marcus Ramirez
    res_m = client.post("/api/auth/login", json={"username": "marcus.ramirez", "password": "password123"})
    assert res_m.status_code == 200
    token_m = res_m.json()["access_token"]
    headers_m = {"Authorization": f"Bearer {token_m}"}

    # Create demo case for Marcus Ramirez
    res_case = client.post("/api/cases/demo", headers=headers_m)
    assert res_case.status_code == 200
    marcus_case = res_case.json()
    assert marcus_case["owner_doctor_id"] == "DOC_MARCUS_RAMIREZ"

    # Marcus queries cases -> must see his case
    res_list = client.get("/api/cases", headers=headers_m)
    assert res_list.status_code == 200
    cases_for_marcus = res_list.json()
    for c in cases_for_marcus:
        # Strict isolation: Marcus must only see Marcus's cases
        assert c["owner_doctor_id"] == "DOC_MARCUS_RAMIREZ"


def test_federated_learning_overview_and_local_training():
    # Get overview
    res = client.get("/api/learning/overview")
    assert res.status_code == 200
    overview = res.json()
    assert "privacy_guarantee" in overview
    assert overview["privacy_guarantee"]["hipaa_safe_harbor_verified"] is True
    assert "weights" in overview

    # Run local DP training step
    res_train = client.post("/api/learning/train-local", json={"epochs": 1, "learning_rate": 0.05})
    assert res_train.status_code == 200
    train_data = res_train.json()
    assert train_data["status"] == "success"
    assert "privacy_proof_hash" in train_data
    assert "epsilon_consumed" in train_data
    assert train_data["epsilon_consumed"] > 0

    # Verify audit log contains entry
    res_audit = client.get("/api/learning/audit")
    assert res_audit.status_code == 200
    audit_data = res_audit.json()
    assert len(audit_data["audit_trail"]) > 0
    latest_entry = audit_data["audit_trail"][0]
    assert latest_entry["l2_grad_norm_after_clip"] <= 1.0001  # Bounded by clip norm


def test_dp_sgd_mathematical_guarantees():
    cfg = DifferentialPrivacyConfig(clip_norm=1.0, noise_multiplier=1.45)
    engine = DifferentialPrivacyEngine(cfg)
    
    # Large gradient that must be clipped
    grad_w = np.array([5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0])
    grad_b = 2.0
    
    noisy_w, noisy_b, pre_norm, post_norm = engine.privatize_gradients(grad_w, grad_b, num_samples=10)
    
    assert pre_norm > 10.0
    assert post_norm <= 1.0001  # Clipped to sensitivity C = 1.0
    assert not np.array_equal(grad_w, noisy_w)  # Noise was added
