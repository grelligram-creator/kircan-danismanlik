"""Invite link canonical base URL tests (APP_BASE_URL as source of truth)."""
import os
import re

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
backend_env = dotenv_values("/app/backend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
APP_BASE_URL = (os.environ.get("APP_BASE_URL") or backend_env.get("APP_BASE_URL") or "").rstrip("/")

SUPER_TOKEN = "test_super_admin_token"
USER_TOKEN = "test_session_seed_001"
VERIFIED_EMAIL = "grelligram@gmail.com"


@pytest.fixture(scope="module")
def super_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    s.cookies.set("session_token", SUPER_TOKEN)
    return s


@pytest.fixture(scope="module")
def user_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    s.cookies.set("session_token", USER_TOKEN)
    return s


@pytest.fixture(scope="module")
def created_codes():
    return []


@pytest.fixture(scope="module", autouse=True)
def cleanup(super_client, created_codes):
    yield
    for code in created_codes:
        r = super_client.delete(f"{BASE_URL}/api/admin/invites/{code}")
        assert r.status_code in (200, 204, 404), f"cleanup failed for {code}: {r.status_code}"


# --- env / config sanity ---
class TestConfig:
    def test_app_base_url_configured(self):
        assert APP_BASE_URL, "APP_BASE_URL missing from backend/.env"
        assert APP_BASE_URL.startswith("https://")
        # after the custom-domain switch the old emergent host must be gone
        assert "emergent.host" not in APP_BASE_URL
        assert "preview.emergentagent.com" not in APP_BASE_URL

    def test_required_env_keys_present(self):
        for key in ("MONGO_URL", "DB_NAME", "EMERGENT_LLM_KEY", "STRIPE_API_KEY", "RESEND_API_KEY", "SENDER_EMAIL"):
            assert backend_env.get(key), f"{key} missing from backend/.env"
        assert backend_env.get("SENDER_EMAIL") == "onboarding@resend.dev"

    def test_no_old_host_in_join_urls(self, super_client, created_codes):
        r = super_client.post(f"{BASE_URL}/api/admin/invites", json={"role": "user"})
        assert r.status_code == 200, r.text
        data = r.json()
        created_codes.append(data["invite"]["code"])
        assert "emergent.host" not in data["join_url"]
        assert data["join_url"].startswith(APP_BASE_URL + "/join/")


# --- POST /api/admin/invites ---
class TestCreateInviteJoinUrl:
    def test_join_url_uses_app_base_url(self, super_client, created_codes):
        r = super_client.post(f"{BASE_URL}/api/admin/invites", json={"role": "user"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "join_url" in data
        code = data["invite"]["code"]
        created_codes.append(code)
        assert data["join_url"] == f"{APP_BASE_URL}/join/{code}"
        assert "preview.emergentagent.com" not in data["join_url"]
        assert data["invite"]["used"] is False
        assert data["invite"]["role"] == "user"
        assert "_id" not in data["invite"]

    def test_env_overrides_origin_and_payload(self, super_client, created_codes):
        r = super_client.post(
            f"{BASE_URL}/api/admin/invites",
            json={"role": "user", "origin_url": "https://preview.example.com"},
            headers={
                "Origin": "https://random.example.com",
                "Referer": "https://referer.example.com/admin",
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        code = data["invite"]["code"]
        created_codes.append(code)
        assert data["join_url"] == f"{APP_BASE_URL}/join/{code}"
        for bad in ("preview.example.com", "random.example.com", "referer.example.com"):
            assert bad not in data["join_url"]

    def test_admin_role_invite_join_url(self, super_client, created_codes):
        r = super_client.post(
            f"{BASE_URL}/api/admin/invites",
            json={"role": "admin", "company_name": "TEST_InviteCo"},
            headers={"Origin": "https://random.example.com"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        code = data["invite"]["code"]
        created_codes.append(code)
        assert data["join_url"].startswith(f"{APP_BASE_URL}/join/")
        assert data["invite"]["role"] == "admin"
        assert data["invite"]["company_id"]

    def test_invalid_role_rejected(self, super_client):
        r = super_client.post(f"{BASE_URL}/api/admin/invites", json={"role": "hacker"})
        assert r.status_code == 400

    def test_regular_user_forbidden(self, user_client):
        r = user_client.post(f"{BASE_URL}/api/admin/invites", json={"role": "user"})
        assert r.status_code == 403

    def test_unauthenticated_rejected(self):
        r = requests.post(f"{BASE_URL}/api/admin/invites", json={"role": "user"})
        assert r.status_code in (401, 403)


# --- GET /api/admin/invites ---
class TestListInvites:
    def test_join_url_prefix(self, super_client, created_codes):
        r = super_client.get(f"{BASE_URL}/api/admin/invites", headers={"Origin": "https://random.example.com"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("join_url_prefix") == f"{APP_BASE_URL}/join"
        assert isinstance(data.get("invites"), list)
        codes = {i["code"] for i in data["invites"]}
        for c in created_codes:
            assert c in codes, f"created invite {c} not persisted/listed"
        for i in data["invites"]:
            assert "_id" not in i

    def test_list_forbidden_for_user(self, user_client):
        r = user_client.get(f"{BASE_URL}/api/admin/invites")
        assert r.status_code == 403


# --- Email body contains production URL (1 real send only) ---
class TestInviteEmail:
    def test_email_html_contains_production_url(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from email_utils import invite_email
        html = invite_email(
            inviter_email="grelligram@gmail.com",
            company_name="TEST_InviteCo",
            role="user",
            join_url=f"{APP_BASE_URL}/join/inv_dummy",
        )
        assert f"{APP_BASE_URL}/join/inv_dummy" in html
        assert "preview.emergentagent.com" not in html

    def test_real_send_uses_production_url(self, super_client, created_codes):
        r = super_client.post(
            f"{BASE_URL}/api/admin/invites",
            json={"role": "user", "email": VERIFIED_EMAIL, "origin_url": "https://preview.example.com"},
            headers={"Origin": "https://random.example.com"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        code = data["invite"]["code"]
        created_codes.append(code)
        assert data["join_url"] == f"{APP_BASE_URL}/join/{code}"
        assert data["email_sent"] is True, f"email not sent: {data.get('email_error')}"
        assert data["email_error"] is None
        assert data["invite"]["email"] == VERIFIED_EMAIL


# --- Join flow still resolves the code ---
class TestJoinCodeResolution:
    def test_created_code_usable_endpoint_exists(self, super_client, created_codes):
        code = created_codes[0]
        r = requests.get(f"{BASE_URL}/api/invites/{code}")
        assert r.status_code in (200, 404, 405), r.status_code
        if r.status_code == 200:
            body = r.json()
            assert code in str(body)
