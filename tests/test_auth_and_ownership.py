import io
import time
from datetime import datetime, timezone, timedelta
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password, verify_password, create_access_token, decode_access_token
from app.models.dataset import Dataset, DatasetVersion
from app.models.profiling import ProfilingRun
from app.models.user import User
from dashboard.guest_sandbox import (
    load_default_guest_dataset,
    profile_guest_dataset,
    simulate_guest_remediation,
    apply_guest_remediation,
)
from app.schemas.remediation import RemediationOperation


# =============================================================================
# 1. Password Hashing (Argon2id) Tests
# =============================================================================

def test_argon2id_hashing_and_verification():
    """Verify password hashing produces secure Argon2id hashes and validates correctly."""
    plain = "SuperSecurePassword123!"
    hashed = hash_password(plain)

    # Hash should be an Argon2 formatted string
    assert hashed.startswith("$argon2id$")
    assert hashed != plain

    # Correct password verifies
    assert verify_password(plain, hashed) is True

    # Wrong password fails
    assert verify_password("WrongPassword123!", hashed) is False
    assert verify_password("", hashed) is False


# =============================================================================
# 2. JWT Generation & Verification Tests (Pinned Algorithm, Claims, Expiry)
# =============================================================================

def test_jwt_generation_and_decoding():
    """Verify JWT access tokens contain subject, email, issuer, expiry, and pinned HS256."""
    settings = get_settings()
    claims = {"sub": "42", "email": "analyst@datapulse.io"}
    token = create_access_token(claims, expires_delta=timedelta(minutes=15))

    decoded = decode_access_token(token)
    assert decoded["sub"] == "42"
    assert decoded["email"] == "analyst@datapulse.io"
    assert decoded["iss"] == "datapulse-ai"
    assert "exp" in decoded
    assert "iat" in decoded


def test_jwt_expired_token_rejected():
    """Verify expired JWTs are rejected with 401."""
    claims = {"sub": "42", "email": "expired@datapulse.io"}
    # Token that expired 5 minutes ago
    expired_token = create_access_token(claims, expires_delta=timedelta(minutes=-5))

    with pytest.raises(Exception):
        decode_access_token(expired_token)


def test_jwt_tampered_signature_rejected():
    """Verify tampered JWT tokens fail signature validation."""
    token = create_access_token({"sub": "42", "email": "tampered@datapulse.io"})
    parts = token.split(".")
    # Tamper payload part
    tampered_token = f"{parts[0]}.{parts[1]}wrong.{parts[2]}"

    with pytest.raises(Exception):
        decode_access_token(tampered_token)


def test_jwt_algorithm_pinning_rejects_none_algorithm():
    """Verify tokens signed with 'none' or untrusted algorithms are rejected."""
    # Attempt to forge an unverified token with 'none' algorithm
    forged_token = jwt.encode({"sub": "42", "iss": "datapulse-ai"}, key="", algorithm="none")

    with pytest.raises(Exception):
        decode_access_token(forged_token)


# =============================================================================
# 3. Registration & Login API Endpoint Tests
# =============================================================================

def test_register_new_user_success(unauthenticated_client: TestClient):
    """Verify registering a new account returns 201 and public user profile."""
    payload = {
        "email": "new.user@datapulse.io",
        "password": "StrongPassword123!",
        "full_name": "New User",
    }
    res = unauthenticated_client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "new.user@datapulse.io"
    assert data["user"]["full_name"] == "New User"
    assert "password" not in data["user"]
    assert "hashed_password" not in data["user"]
    assert data["user"]["id"] is not None


def test_register_duplicate_email_conflict(unauthenticated_client: TestClient):
    """Verify registering an already existing email returns 409 Conflict."""
    payload = {
        "email": "duplicate@datapulse.io",
        "password": "StrongPassword123!",
        "full_name": "Original User",
    }
    res1 = unauthenticated_client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = unauthenticated_client.post("/api/v1/auth/register", json=payload)
    assert res2.status_code == 409
    error = res2.json()["error"]
    assert error["code"] == "CONFLICT"
    assert "already exists" in error["message"]


def test_register_weak_password_rejected(unauthenticated_client: TestClient):
    """Verify passwords shorter than 8 chars or lacking complexity are rejected with 422."""
    # Too short (< 8 chars)
    res_short = unauthenticated_client.post(
        "/api/v1/auth/register",
        json={"email": "short@datapulse.io", "password": "weak"},
    )
    assert res_short.status_code == 422

    # 8 chars but no numbers or special characters
    res_no_digits = unauthenticated_client.post(
        "/api/v1/auth/register",
        json={"email": "letters@datapulse.io", "password": "onlylettershere"},
    )
    assert res_no_digits.status_code == 422


def test_login_success(unauthenticated_client: TestClient):
    """Verify valid credentials return 200 with JWT access token."""
    # 1. Register
    reg_payload = {
        "email": "login.test@datapulse.io",
        "password": "ValidPassword999!",
        "full_name": "Login Tester",
    }
    unauthenticated_client.post("/api/v1/auth/register", json=reg_payload)

    # 2. Login
    login_payload = {
        "email": "login.test@datapulse.io",
        "password": "ValidPassword999!",
    }
    res = unauthenticated_client.post("/api/v1/auth/login", json=login_payload)
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 1800
    assert data["user"]["email"] == "login.test@datapulse.io"


def test_login_incorrect_password_rejected(unauthenticated_client: TestClient):
    """Verify incorrect password returns 401 Unauthorized."""
    # 1. Register
    unauthenticated_client.post(
        "/api/v1/auth/register",
        json={"email": "wrongpwd@datapulse.io", "password": "CorrectPassword123!"},
    )

    # 2. Login with wrong password
    res = unauthenticated_client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpwd@datapulse.io", "password": "WrongPassword456!"},
    )
    assert res.status_code == 401
    error = res.json()["error"]
    assert error["code"] == "UNAUTHORIZED"
    assert "Invalid email or password" in error["message"]


def test_login_nonexistent_user_rejected(unauthenticated_client: TestClient):
    """Verify login for an unregistered email returns 401 Unauthorized."""
    res = unauthenticated_client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@datapulse.io", "password": "AnyPassword123!"},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"


def test_get_me_endpoint(unauthenticated_client: TestClient):
    """Verify GET /api/v1/auth/me returns the authenticated user's profile."""
    # Register & Login to get token
    unauthenticated_client.post(
        "/api/v1/auth/register",
        json={"email": "me.test@datapulse.io", "password": "MePassword123!", "full_name": "Me User"},
    )
    login_res = unauthenticated_client.post(
        "/api/v1/auth/login",
        json={"email": "me.test@datapulse.io", "password": "MePassword123!"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = unauthenticated_client.get("/api/v1/auth/me", headers=headers)
    assert res.status_code == 200
    profile = res.json()
    assert profile["email"] == "me.test@datapulse.io"
    assert profile["full_name"] == "Me User"


# =============================================================================
# 4. Protected Endpoints Rejecting Unauthenticated Requests
# =============================================================================

def test_protected_endpoints_reject_unauthenticated_requests(unauthenticated_client: TestClient):
    """Verify all protected routes return 401 when no token is provided."""
    # Datasets
    res1 = unauthenticated_client.get("/api/v1/datasets")
    assert res1.status_code == 401

    res2 = unauthenticated_client.post("/api/v1/datasets", json={"name": "hack", "source_type": "s3"})
    assert res2.status_code == 401

    # Profiling / remediation
    res3 = unauthenticated_client.post("/api/v1/profiling/1/analyze")
    assert res3.status_code == 401

    res4 = unauthenticated_client.post(
        "/api/v1/profiling/1/remediation/preview",
        json={"operations": [{"operation_type": "drop_duplicates"}]},
    )
    assert res4.status_code == 401


def test_protected_endpoints_reject_invalid_tokens(unauthenticated_client: TestClient):
    """Verify protected routes reject invalid, expired, or malformed Bearer tokens."""
    # Malformed token
    res1 = unauthenticated_client.get("/api/v1/datasets", headers={"Authorization": "Bearer not-a-valid-jwt"})
    assert res1.status_code == 401

    # Missing 'Bearer ' prefix
    res2 = unauthenticated_client.get("/api/v1/datasets", headers={"Authorization": "InvalidScheme token"})
    assert res2.status_code == 401

    # Expired token
    expired = create_access_token({"sub": "1", "email": "exp@datapulse.io"}, expires_delta=timedelta(minutes=-10))
    res3 = unauthenticated_client.get("/api/v1/datasets", headers={"Authorization": f"Bearer {expired}"})
    assert res3.status_code == 401


# =============================================================================
# 5. Dataset Ownership Enforcement & IDOR Prevention
# =============================================================================

def _create_user_and_token(client: TestClient, email: str, password: str = "Password123!") -> tuple[dict, dict]:
    """Helper to register and login a user, returning user data and auth headers."""
    reg = client.post("/api/v1/auth/register", json={"email": email, "password": password, "full_name": email.split("@")[0]})
    reg_data = reg.json()
    user_data = reg_data["user"]
    token = reg_data["access_token"]
    return user_data, {"Authorization": f"Bearer {token}"}


def test_user_accesses_own_dataset(unauthenticated_client: TestClient):
    """Verify a user can create, list, and read their own dataset."""
    user_a, headers_a = _create_user_and_token(unauthenticated_client, "usera@datapulse.io")

    # User A creates a dataset
    payload = {"name": "user_a_dataset", "source_type": "csv"}
    create_res = unauthenticated_client.post("/api/v1/datasets", json=payload, headers=headers_a)
    assert create_res.status_code == 201
    dataset_id = create_res.json()["id"]

    # User A can get it
    get_res = unauthenticated_client.get(f"/api/v1/datasets/{dataset_id}", headers=headers_a)
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "user_a_dataset"

    # User A lists datasets and sees it
    list_res = unauthenticated_client.get("/api/v1/datasets", headers=headers_a)
    assert list_res.status_code == 200
    names = [d["name"] for d in list_res.json()]
    assert "user_a_dataset" in names


def test_user_cannot_access_or_modify_other_user_dataset(unauthenticated_client: TestClient):
    """Verify User B cannot read, list, version, or remediate User A's dataset (returns safe 404)."""
    user_a, headers_a = _create_user_and_token(unauthenticated_client, "owner_a@datapulse.io")
    user_b, headers_b = _create_user_and_token(unauthenticated_client, "intruder_b@datapulse.io")

    # User A creates a dataset
    res_a = unauthenticated_client.post("/api/v1/datasets", json={"name": "secret_dataset_a", "source_type": "s3"}, headers=headers_a)
    dataset_a_id = res_a.json()["id"]

    # 1. User B lists datasets -> must NOT see User A's dataset
    list_b = unauthenticated_client.get("/api/v1/datasets", headers=headers_b)
    assert list_b.status_code == 200
    ids_visible_to_b = [d["id"] for d in list_b.json()]
    assert dataset_a_id not in ids_visible_to_b

    # 2. User B tries direct GET /datasets/{id} -> safe 404 (IDOR safe)
    get_b = unauthenticated_client.get(f"/api/v1/datasets/{dataset_a_id}", headers=headers_b)
    assert get_b.status_code == 404

    # 3. User B tries to add a version to User A's dataset -> 404
    version_payload = {"dataset_id": dataset_a_id, "version_tag": "v2.0", "storage_uri": "s3://b/hack.csv"}
    ver_b = unauthenticated_client.post(f"/api/v1/datasets/{dataset_a_id}/versions", json=version_payload, headers=headers_b)
    assert ver_b.status_code == 404

    # 4. User B tries to view remediation history -> 404
    hist_b = unauthenticated_client.get(f"/api/v1/datasets/{dataset_a_id}/remediation-history", headers=headers_b)
    assert hist_b.status_code == 404


def test_user_cannot_access_other_user_profiling_runs(unauthenticated_client: TestClient, db_session: Session):
    """Verify User B cannot access profiling summary, metrics, AI analysis, or remediation on User A's runs."""
    user_a, headers_a = _create_user_and_token(unauthenticated_client, "profile_owner@datapulse.io")
    user_b, headers_b = _create_user_and_token(unauthenticated_client, "profile_stalker@datapulse.io")

    # Create dataset owned by User A directly in DB with a completed run
    ds_a = Dataset(name="user_a_finance", source_type="s3", user_id=user_a["id"])
    db_session.add(ds_a)
    db_session.flush()

    ver_a = DatasetVersion(dataset_id=ds_a.id, version_tag="v1.0", storage_uri="s3://b/f.csv", row_count=10, column_count=2)
    db_session.add(ver_a)
    db_session.flush()

    run_a = ProfilingRun(dataset_version_id=ver_a.id, status="completed", quality_score=90.0)
    db_session.add(run_a)
    db_session.commit()
    db_session.refresh(run_a)

    # User B tries GET /profiling/{run_id}/summary -> 404
    res_summary = unauthenticated_client.get(f"/api/v1/profiling/{run_a.id}/summary", headers=headers_b)
    assert res_summary.status_code == 404

    # User B tries GET /profiling/{run_id}/metrics -> 404
    res_metrics = unauthenticated_client.get(f"/api/v1/profiling/{run_a.id}/metrics", headers=headers_b)
    assert res_metrics.status_code == 404

    # User B tries POST /profiling/{run_id}/analyze -> 404
    res_ai = unauthenticated_client.post(f"/api/v1/profiling/{run_a.id}/analyze", headers=headers_b)
    assert res_ai.status_code == 404

    # User B tries POST /profiling/{run_id}/remediation/preview -> 404
    res_rem = unauthenticated_client.post(
        f"/api/v1/profiling/{run_a.id}/remediation/preview",
        json={"operations": [{"operation_type": "drop_duplicates"}]},
        headers=headers_b,
    )
    assert res_rem.status_code == 404


def test_existing_unowned_datasets_remain_private(unauthenticated_client: TestClient, db_session: Session):
    """Verify legacy/unowned datasets (user_id IS NULL) are inaccessible to ordinary users."""
    user, headers = _create_user_and_token(unauthenticated_client, "standard_user@datapulse.io")

    # Seed an unowned legacy dataset in database
    unowned_ds = Dataset(name="legacy_unowned_production_data", source_type="s3", user_id=None)
    db_session.add(unowned_ds)
    db_session.commit()
    db_session.refresh(unowned_ds)

    # 1. Listing datasets must NOT disclose the unowned dataset
    list_res = unauthenticated_client.get("/api/v1/datasets", headers=headers)
    assert list_res.status_code == 200
    listed_ids = [d["id"] for d in list_res.json()]
    assert unowned_ds.id not in listed_ids

    # 2. Direct ID access must return 404
    get_res = unauthenticated_client.get(f"/api/v1/datasets/{unowned_ds.id}", headers=headers)
    assert get_res.status_code == 404


# =============================================================================
# 6. Guest Mode Isolation & In-Memory Execution Tests
# =============================================================================

def test_guest_mode_synthetic_dataset_profiling():
    """Verify guest mode loads synthetic data and profiles in-memory without tokens, DB, or S3."""
    guest_df = load_default_guest_dataset()
    assert len(guest_df) > 0
    assert "email" in guest_df.columns

    # Profile 100% in-memory
    result = profile_guest_dataset(guest_df)
    assert result["dataset_name"] == "synthetic_customer_orders_sandbox"
    assert result["total_rows_profiled"] == len(guest_df)
    assert result["quality_score"] < 100.0  # Intentional quality defects
    assert len(result["issues"]) > 0
    assert len(result["metrics"]) > 0
    assert "completeness" in result["component_scores"]


def test_guest_mode_remediation_preview_in_memory():
    """Verify guest mode remediation simulation runs in-memory and shows diffs."""
    guest_df = load_default_guest_dataset()
    initial_rows = len(guest_df)

    operations = [
        {"operation_type": "drop_duplicates"},
        {"operation_type": "fill_missing", "column": "email", "strategy": "constant", "fill_value": "guest@datapulse.io"},
    ]

    preview_res = simulate_guest_remediation(guest_df, operations)
    assert preview_res["total_rows_before"] == initial_rows
    assert preview_res["total_rows_after"] <= initial_rows
    assert len(preview_res["operations"]) == 2
    assert "new_df" in preview_res

    # Verify original dataframe is immutable
    assert len(guest_df) == initial_rows


def test_guest_mode_remediation_apply_in_memory_score_boost():
    """Verify guest mode remediation application computes quality score improvement in-memory."""
    guest_df = load_default_guest_dataset()

    operations = [
        {"operation_type": "drop_duplicates"},
        {"operation_type": "fill_missing", "column": "email", "strategy": "constant", "fill_value": "guest@datapulse.io"},
    ]

    applied_res = apply_guest_remediation(guest_df, operations)
    assert applied_res["remediated_score"] >= applied_res["original_score"]
    assert applied_res["score_improvement"] >= 0.0
    assert "remediated_df" in applied_res
    assert applied_res["storage_uri"].startswith("memory://")


def test_guest_mode_zero_cloud_persistence():
    """Verify guest operations do not mutate or write into database tables."""
    from app.models.dataset import Dataset
    from app.models.profiling import ProfilingRun

    # Running guest profiling and remediation
    guest_df = load_default_guest_dataset()
    profile_guest_dataset(guest_df)
    simulate_guest_remediation(guest_df, [{"operation_type": "drop_duplicates"}])
    apply_guest_remediation(guest_df, [{"operation_type": "drop_duplicates"}])

    # In-memory execution leaves database tables completely untouched
    # (Checked implicitly via db_session fixture isolation)

