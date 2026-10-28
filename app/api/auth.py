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
import re
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

# Active session revocation list (in-memory & disk-backed with TTL eviction)
_REVOKED_TOKEN_EXPIRIES: Dict[str, float] = {}
_REVOKED_LOCK = threading.Lock()
REVOKED_TOKENS_FILE = DATA_DIR / "revoked_tokens.json"


def _load_revoked_tokens() -> None:
    global _REVOKED_TOKEN_EXPIRIES
    if REVOKED_TOKENS_FILE.is_file():
        try:
            with open(REVOKED_TOKENS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                now = time.time()
                _REVOKED_TOKEN_EXPIRIES = {k: float(v) for k, v in data.items() if float(v) > now}
        except Exception:
            pass


def _save_revoked_tokens() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp = REVOKED_TOKENS_FILE.with_suffix(f".tmp_{secrets.token_hex(4)}")
    try:
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(_REVOKED_TOKEN_EXPIRIES, f)
        temp.replace(REVOKED_TOKENS_FILE)
    except Exception:
        pass


# Login rate-limiting and brute force lockout (composite IP + username, thread-safe)
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

def _canonical_username(u: str) -> str:
    """Canonicalizes usernames to lowercase alphanumerics for collision prevention."""
    return re.sub(r"[._\-]", "", u.lower().strip())


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
    """Revokes a session bearer token immediately and persists with TTL."""
    try:
        parts = token.split(".")
        if len(parts) == 2:
            sig = parts[1]
            now = time.time()
            exp = now + TOKEN_EXPIRY_HOURS * 3600
            try:
                # Extract exp from payload if possible
                pad = len(parts[0]) % 4
                p_b64 = parts[0] + ("=" * (4 - pad) if pad else "")
                payload = json.loads(base64.urlsafe_b64decode(p_b64.encode("utf-8")))
                exp = float(payload.get("exp", exp))
            except Exception:
                pass
            with _REVOKED_LOCK:
                if not _REVOKED_TOKEN_EXPIRIES:
                    _load_revoked_tokens()
                _REVOKED_TOKEN_EXPIRIES[sig] = exp
                # Evict expired
                expired = [k for k, v in _REVOKED_TOKEN_EXPIRIES.items() if v < now]
                for k in expired:
                    del _REVOKED_TOKEN_EXPIRIES[k]
                _save_revoked_tokens()
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
            now = time.time()
            with _REVOKED_LOCK:
                if not _REVOKED_TOKEN_EXPIRIES:
                    _load_revoked_tokens()
                exp = _REVOKED_TOKEN_EXPIRIES.get(sig)
                if exp is not None:
                    if exp < now:
                        del _REVOKED_TOKEN_EXPIRIES[sig]
                        return False
                    return True
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


def _check_rate_limit(username: str, client_ip: str = "127.0.0.1") -> None:
    """Enforces lockout after MAX_LOGIN_ATTEMPTS failures keyed on composite client IP + canonical username."""
    now = time.time()
    key = f"{client_ip}:{_canonical_username(username)}"
    with _LOGIN_LOCK:
        # Periodic purge of stale entries
        for k in list(_LOGIN_FAILURES.keys()):
            _LOGIN_FAILURES[k] = [t for t in _LOGIN_FAILURES[k] if now - t < LOCKOUT_DURATION_SECONDS]
            if not _LOGIN_FAILURES[k]:
                del _LOGIN_FAILURES[k]
        attempts = _LOGIN_FAILURES.get(key, [])
        if len(attempts) >= MAX_LOGIN_ATTEMPTS:
            remaining_mins = max(1, int((LOCKOUT_DURATION_SECONDS - (now - attempts[0])) // 60))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Security Lockout: Account temporarily locked due to {MAX_LOGIN_ATTEMPTS} failed attempts. Please retry in {remaining_mins} minutes."
            )


def _record_login_failure(username: str, client_ip: str = "127.0.0.1") -> None:
    now = time.time()
    key = f"{client_ip}:{_canonical_username(username)}"
    with _LOGIN_LOCK:
        _LOGIN_FAILURES.setdefault(key, []).append(now)


def _reset_login_failures(username: str, client_ip: str = "127.0.0.1") -> None:
    key = f"{client_ip}:{_canonical_username(username)}"
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
        is_prod = os.getenv("ACUCALYX_ENV") == "production"
        doctors: Dict[str, DoctorInDB] = {}
        if is_prod:
            admin_user = os.getenv("ACUCALYX_ADMIN_USERNAME")
            admin_pwd = os.getenv("ACUCALYX_ADMIN_PASSWORD")
            if admin_user and admin_pwd:
                salt, pwd_hash = hash_password(admin_pwd, iterations=PBKDF2_RECOMMENDED_ITERATIONS)
                admin_doc = DoctorInDB(
                    doctor_id=f"DOC_{secrets.token_hex(6).upper()}",
                    username=admin_user,
                    full_name="Hospital System Administrator",
                    title="Chief Medical Informatics Officer",
                    department="Clinical Administration",
                    institution="Hospital Health System",
                    npi="1000000001",
                    email=f"{admin_user}@hospital.org",
                    role="ADMIN",
                    avatar_color="#0284c7",
                    salt_hex=salt,
                    password_hash_hex=pwd_hash,
                    created_at=datetime.now(timezone.utc).isoformat()
                )
                doctors[admin_doc.doctor_id] = admin_doc
                _save_doctors_db(doctors)
                _DOCTORS_CACHE = doctors
                _DOCTORS_CACHE_MTIME = DOCTORS_FILE.stat().st_mtime if DOCTORS_FILE.is_file() else 0.0
                return dict(doctors)
            # In production with no admin env vars and no db file, return empty dict to avoid hardcoded default credentials
            _DOCTORS_CACHE = {}
            return {}

        for item in DEFAULT_DOCTORS:
            salt, pwd_hash = hash_password(item["password"], iterations=PBKDF2_RECOMMENDED_ITERATIONS)
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
def login_doctor(req: DoctorLoginRequest, response: Response, request: Request):
    """Authenticates doctor credentials and issues signed session bearer token with rate-limit protection."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    elif request.client:
        client_ip = request.client.host
    else:
        client_ip = "127.0.0.1"
    _check_rate_limit(req.username, client_ip)
    doctors = _ensure_doctors_db()

    # Find doctor by username or email (case-insensitive and canonical match)
    matched_doc: Optional[DoctorInDB] = None
    req_canon = _canonical_username(req.username)
    for d in doctors.values():
        if _canonical_username(d.username) == req_canon or d.email.lower() == req.username.lower():
            matched_doc = d
            break

    if not matched_doc or not verify_password(req.password, matched_doc.salt_hex, matched_doc.password_hash_hex):
        _record_login_failure(req.username, client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid clinical credentials. Please check your username/email and password."
        )

    _reset_login_failures(req.username, client_ip)

    # Transparent security upgrade for accounts with legacy 100k iteration hashes
    try:
        salt_bytes = bytes.fromhex(matched_doc.salt_hex)
        key_legacy = hashlib.pbkdf2_hmac("sha256", req.password.encode("utf-8"), salt_bytes, PBKDF2_LEGACY_ITERATIONS)
        if hmac.compare_digest(key_legacy.hex(), matched_doc.password_hash_hex):
            new_salt, new_hash = hash_password(req.password, iterations=PBKDF2_RECOMMENDED_ITERATIONS)
            matched_doc.salt_hex = new_salt
            matched_doc.password_hash_hex = new_hash
            doctors[matched_doc.doctor_id] = matched_doc
            _save_doctors_db(doctors)
            logger.info(f"Transparently upgraded password security to 600k iterations for {matched_doc.username}")
    except Exception as e:
        logger.warning(f"Legacy password upgrade check failed: {e}")

    token = create_access_token(matched_doc.doctor_id, matched_doc.username, matched_doc.role)
    doc_profile = Doctor(**matched_doc.model_dump(exclude={"salt_hex", "password_hash_hex"}))

    is_prod = os.getenv("ACUCALYX_ENV") == "production"
    response.set_cookie(
        key="acucalyx_token",
        value=token,
        httponly=True,
        secure=is_prod,
        samesite="strict" if is_prod else "lax",
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
    Registers a new doctor profile with strict role validation and collision prevention.
    Privileged roles (CHIEF_SURGEON, ADMIN) cannot be self-assigned.
    """
    is_prod = os.getenv("ACUCALYX_ENV") == "production"
    if is_prod and os.getenv("ACUCALYX_ALLOW_REGISTRATION", "0") != "1":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public self-registration is disabled in production. An administrator must provision your account."
        )

    # Password complexity policy
    if len(req.password) < 8 or not any(c.isupper() for c in req.password) or not any(c.isdigit() for c in req.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password policy requirement: minimum 8 characters, at least one uppercase letter and one number."
        )

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

    # Check if canonical username or email already exists (treats '.', '_', '-' as identical to block account takeover)
    req_canon = _canonical_username(req.username)
    for d in doctors.values():
        if _canonical_username(d.username) == req_canon:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username is already in use by another physician.")
        if d.email.lower() == req.email.lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email address is already registered.")

    # Unique random doctor ID to prevent ID collision and takeover
    doctor_id = f"DOC_{secrets.token_hex(6).upper()}"
    while doctor_id in doctors:
        doctor_id = f"DOC_{secrets.token_hex(6).upper()}"

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
        secure=is_prod,
        samesite="strict" if is_prod else "lax",
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
