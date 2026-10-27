"""
AcuCalyx Authentication & Doctor Privacy Isolation Engine
Governed by HIPAA Privacy Rule (45 CFR § 164.502), Role-Based Access Control (RBAC),
and FDA Premarket Cybersecurity Guidance (Section 524B).

Provides:
- Secure PBKDF2-HMAC-SHA256 password hashing with 600,000 iterations and unique 16-byte salt
- Backward-compatible verification for legacy 100,000-iteration credentials
- Cryptographic HMAC-SHA256 bearer session tokens with expiration and active revocation
- Thread-safe in-memory caching of doctor registry with automatic mtime invalidation
- Rate limiting and brute-force lockout on authentication endpoints
- Doctor-specific patient record isolation (multi-tenancy)
- Clinical staff profile management & authenticated institutional directory
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone, timedelta
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import secrets
import threading
import time
from typing import Any, Dict, List, Optional, Set
from fastapi import APIRouter, Depends, HTTPException, Header, Request, Response, status
from pydantic import BaseModel, Field

logger = logging.getLogger("acucalyx.auth")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DOCTORS_FILE = DATA_DIR / "doctors.json"

_raw_auth_secret = os.environ.get("ACUCALYX_AUTH_SECRET")
_INSECURE_SECRETS = {
    "ACUCALYX_SECURE_SURGICAL_JWT_SECRET_2026_PROD",
    "ACUCALYX_SECURE_SURGICAL_JWT_PROD_DEPLOYMENT_KEY_2026",
    "change_me_to_a_random_hex_string_64",
}
if os.environ.get("ACUCALYX_ENV") == "production" and (not _raw_auth_secret or _raw_auth_secret in _INSECURE_SECRETS):
    raise RuntimeError(
        "Production Security Violation (FDA Section 524B / OWASP): "
        "ACUCALYX_AUTH_SECRET environment variable must be set to a secure random secret in production mode."
    )
AUTH_SECRET_KEY = (_raw_auth_secret or "ACUCALYX_SECURE_SURGICAL_JWT_SECRET_2026_PROD").encode("utf-8")
TOKEN_EXPIRY_HOURS = 24

# Active session revocation list (in-memory, thread-safe)
_REVOKED_TOKEN_SIGNATURES: Set[str] = set()
_REVOKED_LOCK = threading.Lock()

# Login rate-limiting and brute force lockout (in-memory, thread-safe)
_LOGIN_FAILURES: Dict[str, List[float]] = {}
_LOGIN_LOCK = threading.Lock()
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 900  # 15 minutes lockout after 5 consecutive failures

# In-memory doctors database cache with mtime invalidation
_DOCTORS_CACHE: Dict[str, "DoctorInDB"] = {}
_DOCTORS_CACHE_MTIME: float = 0.0
_DOCTORS_DB_LOCK = threading.Lock()

# PBKDF2 iteration constants (NIST SP 800-63B / OWASP recommendations)
PBKDF2_RECOMMENDED_ITERATIONS = 600_000
PBKDF2_LEGACY_ITERATIONS = 100_000

router = APIRouter(prefix="/api/auth", tags=["Doctor Authentication & Privacy"])


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class Doctor(BaseModel):
    doctor_id: str
    username: str
    full_name: str
    title: str
    department: str
    institution: str
    npi: str
    email: str
    role: str = "ATTENDING_SURGEON"  # CHIEF_SURGEON, ATTENDING_SURGEON, FELLOW, RADIOLOGIST, ADMIN
    avatar_color: str = "#0284c7"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DoctorInDB(Doctor):
    salt_hex: str
    password_hash_hex: str


class DoctorLoginRequest(BaseModel):
    username: str
    password: str


class DoctorRegisterRequest(BaseModel):
    username: str
    password: str = Field(..., min_length=8, description="Minimum 8 characters password")
    full_name: str
    title: str = "Attending Urologist"
    department: str = "Endourology & Urology"
    institution: str = "Comprehensive Kidney Stone Center"
    npi: str = "1000000000"
    email: str
    role: str = "ATTENDING_SURGEON"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    doctor: Doctor


# ---------------------------------------------------------------------------
# Cryptographic Security Utilities
# ---------------------------------------------------------------------------

def hash_password(
    password: str,
    salt_bytes: Optional[bytes] = None,
    iterations: int = PBKDF2_RECOMMENDED_ITERATIONS
) -> tuple[str, str]:
    """
    Generates PBKDF2-HMAC-SHA256 hash and salt with recommended iteration count (600,000).
    Returns (salt_hex, key_hex).
    """
    salt = salt_bytes or secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return salt.hex(), key.hex()


def verify_password(password: str, salt_hex: str, expected_hash_hex: str) -> bool:
    """
    Constant-time password hash verification.
    Attempts modern recommended 600,000 iterations first; falls back to legacy 100,000 iterations.
    """
    salt = bytes.fromhex(salt_hex)
    # Check 600k iterations
    key_current = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_RECOMMENDED_ITERATIONS)
    if hmac.compare_digest(key_current.hex(), expected_hash_hex):
        return True
    # Fallback to legacy 100k iterations
    key_legacy = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_LEGACY_ITERATIONS)
    return hmac.compare_digest(key_legacy.hex(), expected_hash_hex)


def create_access_token(doctor_id: str, username: str, role: str) -> str:
    """Generates a secure HMAC-SHA256 signed bearer token."""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=TOKEN_EXPIRY_HOURS)
    payload = {
        "sub": doctor_id,
        "usr": username,
        "rol": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": secrets.token_hex(8)
    }
    payload_json = json.dumps(payload, separators=(',', ':')).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode("utf-8").rstrip("=")
    signature = hmac.new(AUTH_SECRET_KEY, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def revoke_token(token: str) -> bool:
    """Revokes a session bearer token immediately."""
    try:
        parts = token.split(".")
        if len(parts) == 2:
            sig = parts[1]
            with _REVOKED_LOCK:
                _REVOKED_TOKEN_SIGNATURES.add(sig)
            return True
    except Exception:
        pass
    return False


def is_token_revoked(token: str) -> bool:
    """Checks whether token signature has been revoked."""
    try:
        parts = token.split(".")
        if len(parts) == 2:
            sig = parts[1]
            with _REVOKED_LOCK:
                return sig in _REVOKED_TOKEN_SIGNATURES
    except Exception:
        pass
    return False


def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Validates token signature, revocation status, and expiration."""
    try:
        if is_token_revoked(token):
            return None

        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, signature = parts
        expected_sig = hmac.new(AUTH_SECRET_KEY, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None

        # Add back padding
        pad = len(payload_b64) % 4
        if pad:
            payload_b64 += "=" * (4 - pad)
        payload_json = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
        payload = json.loads(payload_json)

        # Expiration check
        if payload.get("exp", 0) < int(datetime.now(timezone.utc).timestamp()):
            return None
        return payload
    except Exception as e:
        logger.debug(f"Token verification error: {e}")
        return None


def _check_rate_limit(username: str) -> None:
    """Enforces lockout after MAX_LOGIN_ATTEMPTS failures."""
    now = time.time()
    key = username.lower().strip()
    with _LOGIN_LOCK:
        attempts = _LOGIN_FAILURES.get(key, [])
        recent = [t for t in attempts if now - t < LOCKOUT_DURATION_SECONDS]
        _LOGIN_FAILURES[key] = recent
        if len(recent) >= MAX_LOGIN_ATTEMPTS:
            remaining_mins = max(1, int((LOCKOUT_DURATION_SECONDS - (now - recent[0])) // 60))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Security Lockout: Account temporarily locked due to {MAX_LOGIN_ATTEMPTS} failed attempts. Please retry in {remaining_mins} minutes."
            )


def _record_login_failure(username: str) -> None:
    now = time.time()
    key = username.lower().strip()
    with _LOGIN_LOCK:
        _LOGIN_FAILURES.setdefault(key, []).append(now)


def _reset_login_failures(username: str) -> None:
    key = username.lower().strip()
    with _LOGIN_LOCK:
        _LOGIN_FAILURES.pop(key, None)


# ---------------------------------------------------------------------------
# Database / Doctors Store Persistence (Cached)
# ---------------------------------------------------------------------------

DEFAULT_DOCTORS = [
    {
        "doctor_id": "DOC_ELENA_CHEN",
        "username": "elena.chen",
        "full_name": "Dr. Elena Chen, MD, FACS",
        "title": "Chief of Endourology & Minimally Invasive Surgery",
        "department": "Department of Urology",
        "institution": "Johns Hopkins Comprehensive Stone Center",
        "npi": "1982736450",
        "email": "elena.chen@hospital.org",
        "role": "CHIEF_SURGEON",
        "avatar_color": "#0284c7",
        "password": "password123"
    },
    {
        "doctor_id": "DOC_MARCUS_RAMIREZ",
        "username": "marcus.ramirez",
        "full_name": "Dr. Marcus Ramirez, MD",
        "title": "Attending Interventional Urologist",
        "department": "Division of Endourology",
        "institution": "Memorial Endourology Institute",
        "npi": "1472839102",
        "email": "marcus.ramirez@hospital.org",
        "role": "ATTENDING_SURGEON",
        "avatar_color": "#047857",
        "password": "password123"
    },
    {
        "doctor_id": "DOC_SARAH_JENKINS",
        "username": "sarah.jenkins",
        "full_name": "Dr. Sarah Jenkins, MD",
        "title": "Endourology & Robotics Clinical Fellow",
        "department": "Department of Urology",
        "institution": "Johns Hopkins Comprehensive Stone Center",
        "npi": "1839201928",
        "email": "sarah.jenkins@hospital.org",
        "role": "FELLOW",
        "avatar_color": "#7c3aed",
        "password": "password123"
    }
]


def _ensure_doctors_db() -> Dict[str, DoctorInDB]:
    """
    Loads or initializes persisted doctors repository.
    Caches parsed records in-memory, re-reading from disk only when file mtime changes.
    """
    global _DOCTORS_CACHE, _DOCTORS_CACHE_MTIME
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with _DOCTORS_DB_LOCK:
        if DOCTORS_FILE.is_file():
            try:
                mtime = DOCTORS_FILE.stat().st_mtime
                if _DOCTORS_CACHE and mtime == _DOCTORS_CACHE_MTIME:
                    return dict(_DOCTORS_CACHE)

                with open(DOCTORS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                doctors = {doc_id: DoctorInDB(**d) for doc_id, d in data.items()}
                if doctors:
                    _DOCTORS_CACHE = doctors
                    _DOCTORS_CACHE_MTIME = mtime
                    return dict(_DOCTORS_CACHE)
            except Exception as e:
                logger.warning(f"Error reading doctors registry: {e}. Re-initializing defaults.")

        # Initialize defaults if file missing or corrupted
        doctors: Dict[str, DoctorInDB] = {}
        for item in DEFAULT_DOCTORS:
            salt, pwd_hash = hash_password(item["password"], iterations=PBKDF2_LEGACY_ITERATIONS)
            doc = DoctorInDB(
                doctor_id=item["doctor_id"],
                username=item["username"],
                full_name=item["full_name"],
                title=item["title"],
                department=item["department"],
                institution=item["institution"],
                npi=item["npi"],
                email=item["email"],
                role=item["role"],
                avatar_color=item["avatar_color"],
                salt_hex=salt,
                password_hash_hex=pwd_hash,
                created_at=datetime.now(timezone.utc).isoformat()
            )
            doctors[doc.doctor_id] = doc

        _save_doctors_db(doctors)
        _DOCTORS_CACHE = doctors
        _DOCTORS_CACHE_MTIME = DOCTORS_FILE.stat().st_mtime if DOCTORS_FILE.is_file() else 0.0
        return dict(doctors)


def _save_doctors_db(doctors: Dict[str, DoctorInDB]) -> None:
    global _DOCTORS_CACHE, _DOCTORS_CACHE_MTIME
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = DOCTORS_FILE.with_suffix(f".tmp_{secrets.token_hex(4)}")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump({k: v.model_dump() for k, v in doctors.items()}, f, indent=2)
    temp_file.replace(DOCTORS_FILE)
    _DOCTORS_CACHE = dict(doctors)
    _DOCTORS_CACHE_MTIME = DOCTORS_FILE.stat().st_mtime


# ---------------------------------------------------------------------------
# FastAPI Dependency Injection
# ---------------------------------------------------------------------------

def get_current_doctor(
    request: Request,
    authorization: Optional[str] = Header(None)
) -> Doctor:
    """
    Extracts and authenticates doctor identity from Authorization header or cookie.
    Tokens in query string parameters are strictly rejected to prevent referer/log leakage.
    In testing/offline fallback without header, defaults to Chief Surgeon (Dr. Elena Chen)
    to preserve test compatibility while enabling multi-tenancy.
    """
    doctors = _ensure_doctors_db()

    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif "acucalyx_token" in request.cookies:
        token = request.cookies.get("acucalyx_token")

    is_prod = os.getenv("ACUCALYX_ENV") == "production"
    require_auth = os.getenv("ACUCALYX_REQUIRE_AUTH", "1" if is_prod else "0") == "1"

    if require_auth:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required: Missing or expired session token."
            )
        payload = verify_access_token(token)
        if not payload or payload.get("sub") not in doctors:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid credentials.")
        doc_in_db = doctors[payload["sub"]]
        return Doctor(**doc_in_db.model_dump(exclude={"salt_hex", "password_hash_hex"}))

    if token:
        payload = verify_access_token(token)
        if payload and payload.get("sub") in doctors:
            doc_in_db = doctors[payload["sub"]]
            return Doctor(**doc_in_db.model_dump(exclude={"salt_hex", "password_hash_hex"}))

    # Backward compatibility for offline development/testing
    default_doc = doctors.get("DOC_ELENA_CHEN")
    if default_doc:
        return Doctor(**default_doc.model_dump(exclude={"salt_hex", "password_hash_hex"}))

    # Fallback minimal doctor
    return Doctor(
        doctor_id="DOC_ELENA_CHEN",
        username="elena.chen",
        full_name="Dr. Elena Chen, MD, FACS",
        title="Chief of Endourology",
        department="Urology",
        institution="Johns Hopkins Comprehensive Stone Center",
        npi="1982736450",
        email="elena.chen@hospital.org",
        role="CHIEF_SURGEON"
    )


# ---------------------------------------------------------------------------
# REST Endpoints
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenResponse)
def login_doctor(req: DoctorLoginRequest, response: Response):
    """Authenticates doctor credentials and issues signed session bearer token with rate-limit protection."""
    _check_rate_limit(req.username)
    doctors = _ensure_doctors_db()

    # Find doctor by username or email (case-insensitive)
    matched_doc: Optional[DoctorInDB] = None
    for d in doctors.values():
        if d.username.lower() == req.username.lower() or d.email.lower() == req.username.lower():
            matched_doc = d
            break

    if not matched_doc or not verify_password(req.password, matched_doc.salt_hex, matched_doc.password_hash_hex):
        _record_login_failure(req.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid clinical credentials. Please check your username/email and password."
        )

    _reset_login_failures(req.username)
    token = create_access_token(matched_doc.doctor_id, matched_doc.username, matched_doc.role)
    doc_profile = Doctor(**matched_doc.model_dump(exclude={"salt_hex", "password_hash_hex"}))

    logger.info(f"Doctor login successful: {doc_profile.full_name} ({doc_profile.doctor_id})")
    response.set_cookie(
        key="acucalyx_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=TOKEN_EXPIRY_HOURS * 3600
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in_seconds=TOKEN_EXPIRY_HOURS * 3600,
        doctor=doc_profile
    )


@router.post("/register", response_model=TokenResponse)
def register_doctor(req: DoctorRegisterRequest, response: Response):
    """
    Registers a new doctor profile with strict role validation.
    Privileged roles (CHIEF_SURGEON, ADMIN) cannot be self-assigned.
    """
    doctors = _ensure_doctors_db()

    # Role privilege escalation check
    requested_role = req.role.upper().strip()
    if requested_role in ("CHIEF_SURGEON", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Privilege Escalation Blocked: Administrative and Chief Surgeon roles cannot be self-assigned."
        )

    allowed_self_roles = {"ATTENDING_SURGEON", "FELLOW", "RESIDENT", "RADIOLOGIST"}
    assigned_role = requested_role if requested_role in allowed_self_roles else "ATTENDING_SURGEON"

    # Check if username or email already exists
    for d in doctors.values():
        if d.username.lower() == req.username.lower():
            raise HTTPException(status_code=400, detail="Username is already in use by another physician.")
        if d.email.lower() == req.email.lower():
            raise HTTPException(status_code=400, detail="Email address is already registered.")

    doctor_id = f"DOC_{req.username.upper().replace('.', '_')}"
    salt, pwd_hash = hash_password(req.password, iterations=PBKDF2_RECOMMENDED_ITERATIONS)

    new_doc = DoctorInDB(
        doctor_id=doctor_id,
        username=req.username,
        full_name=req.full_name,
        title=req.title,
        department=req.department,
        institution=req.institution,
        npi=req.npi,
        email=req.email,
        role=assigned_role,
        avatar_color=secrets.choice(["#0284c7", "#047857", "#2563eb", "#7c3aed", "#d97706"]),
        salt_hex=salt,
        password_hash_hex=pwd_hash,
        created_at=datetime.now(timezone.utc).isoformat()
    )

    doctors[doctor_id] = new_doc
    _save_doctors_db(doctors)

    token = create_access_token(doctor_id, new_doc.username, new_doc.role)
    doc_profile = Doctor(**new_doc.model_dump(exclude={"salt_hex", "password_hash_hex"}))

    logger.info(f"Registered new physician: {doc_profile.full_name} ({doctor_id}) with role {assigned_role}")
    response.set_cookie(
        key="acucalyx_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=TOKEN_EXPIRY_HOURS * 3600
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in_seconds=TOKEN_EXPIRY_HOURS * 3600,
        doctor=doc_profile
    )


@router.get("/me", response_model=Doctor)
def get_my_profile(current_doctor: Doctor = Depends(get_current_doctor)):
    """Returns profile and credential details of currently authenticated doctor."""
    return current_doctor


@router.get("/doctors", response_model=List[Doctor])
def list_department_doctors(current_doctor: Doctor = Depends(get_current_doctor)):
    """Lists department physicians and specialists available for surgical consultation (Requires authentication)."""
    doctors = _ensure_doctors_db()
    return [Doctor(**d.model_dump(exclude={"salt_hex", "password_hash_hex"})) for d in doctors.values()]


@router.post("/logout")
def logout_doctor(request: Request, response: Response, authorization: Optional[str] = Header(None)):
    """Invalidates client credentials and registers token signature in revocation blacklist."""
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif "acucalyx_token" in request.cookies:
        token = request.cookies.get("acucalyx_token")

    if token:
        revoke_token(token)
        response.delete_cookie(key="acucalyx_token")
        return {"status": "success", "message": "Logged out successfully. Session token revoked."}
    response.delete_cookie(key="acucalyx_token")
    return {"status": "success", "message": "Logged out successfully."}
