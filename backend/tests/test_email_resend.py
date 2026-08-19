"""Resend email integration tests: report email + invite email.

Sends at most 2 real emails (to the verified account owner address).
"""
import os
import time

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

SUPER_TOKEN = "test_super_admin_token"
USER_TOKEN = "test_session_seed_001"
SUPER_EMAIL = "grelligram@gmail.com"


def client(token):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    s.cookies.set("session_token", token)
    return s


@pytest.fixture(scope="module")
def sa():
    return client(SUPER_TOKEN)


@pytest.fixture(scope="module")
def usr():
    return client(USER_TOKEN)


@pytest.fixture(scope="module")
def created(sa):
    """Track created chats/invites for cleanup."""
    bag = {"chats": [], "invites": []}
    yield bag
    for c in bag["chats"]:
        sa.delete(f"{BASE_URL}/api/chats/{c}", timeout=30)
    for code in bag["invites"]:
        sa.delete(f"{BASE_URL}/api/admin/invites/{code}", timeout=30)


# ---------- health / auth ----------
class TestAuth:
    def test_super_admin_me(self, sa):
        r = sa.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["email"] == SUPER_EMAIL
        assert d["role"] == "super_admin"

    def test_regular_user_me(self, usr):
        r = usr.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["role"] == "user"


# ---------- report email (real Resend send #1) ----------
class TestReportEmail:
    def test_email_report_real_send(self, sa, created):
        cr = sa.post(f"{BASE_URL}/api/chats", json={"mode": "report"}, timeout=60)
        assert cr.status_code == 200, cr.text[:300]
        chat = cr.json()
        chat_id = chat.get("chat_id") or chat.get("chat", {}).get("chat_id")
        assert chat_id
        created["chats"].append(chat_id)

        r = sa.post(f"{BASE_URL}/api/chats/{chat_id}/email", timeout=120)
        assert r.status_code == 200, r.text[:500]
        d = r.json()
        assert d["success"] is True
        assert d["sent_to"] == SUPER_EMAIL
        assert isinstance(d.get("message_id"), str) and len(d["message_id"]) > 10
        assert "mock" not in d, f"legacy mock field still present: {d}"
        TestReportEmail.msg_id = d["message_id"]
        TestReportEmail.chat_id = chat_id

    def test_email_log_persisted(self, sa):
        chat_id = getattr(TestReportEmail, "chat_id", None)
        if not chat_id:
            pytest.fail("previous send test did not run")
        import subprocess
        import json as _json
        out = subprocess.run(
            ["mongosh", os.environ.get("MONGO_URL", "mongodb://localhost:27017") + "/test_database",
             "--quiet", "--eval",
             f'JSON.stringify(db.email_logs.findOne({{chat_id:"{chat_id}"}}))'],
            capture_output=True, text=True, timeout=60,
        )
        raw = out.stdout.strip()
        assert raw and raw != "null", f"no email_log row: {raw} {out.stderr[:200]}"
        log = _json.loads(raw)
        assert log["provider"] == "resend"
        assert log["provider_message_id"] == TestReportEmail.msg_id
        assert log["email"] == SUPER_EMAIL

    def test_email_report_foreign_chat_404(self, sa, usr, created):
        cr = usr.post(f"{BASE_URL}/api/chats", json={"mode": "report"}, timeout=60)
        assert cr.status_code == 200, cr.text[:300]
        chat = cr.json()
        other_chat = chat.get("chat_id") or chat.get("chat", {}).get("chat_id")
        r = sa.post(f"{BASE_URL}/api/chats/{other_chat}/email", timeout=60)
        assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:300]}"
        usr.delete(f"{BASE_URL}/api/chats/{other_chat}", timeout=30)

    def test_email_report_unknown_chat_404(self, sa):
        r = sa.post(f"{BASE_URL}/api/chats/chat_doesnotexist/email", timeout=60)
        assert r.status_code == 404, r.text[:300]

    def test_email_report_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/chats/chat_x/email", timeout=30)
        assert r.status_code in (401, 403), r.status_code


# ---------- invites ----------
class TestInviteEmail:
    def test_invite_without_email(self, sa, created):
        r = sa.post(f"{BASE_URL}/api/admin/invites", json={"role": "user"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["email_sent"] is False
        assert d["email_error"] is None
        inv = d["invite"]
        assert inv["code"].startswith("inv_")
        assert inv["email"] is None
        assert inv["used"] is False
        assert "_id" not in inv
        created["invites"].append(inv["code"])

    def test_invite_with_verified_email_real_send(self, sa, created):
        time.sleep(1)
        r = sa.post(f"{BASE_URL}/api/admin/invites", json={
            "role": "user", "email": SUPER_EMAIL, "origin_url": BASE_URL,
        }, timeout=90)
        assert r.status_code == 200, r.text[:500]
        d = r.json()
        assert d["email_error"] is None, f"email_error: {d['email_error']}"
        assert d["email_sent"] is True
        assert d["invite"]["email"] == SUPER_EMAIL
        created["invites"].append(d["invite"]["code"])

    def test_invite_with_unverified_email_graceful(self, sa, created):
        time.sleep(1)
        r = sa.post(f"{BASE_URL}/api/admin/invites", json={
            "role": "user", "email": "test_qa_unverified@example.com", "origin_url": BASE_URL,
        }, timeout=90)
        assert r.status_code == 200, r.text[:500]
        d = r.json()
        assert d["email_sent"] is False
        assert isinstance(d["email_error"], str) and d["email_error"]
        # invite must still be created & persisted
        code = d["invite"]["code"]
        created["invites"].append(code)
        lr = sa.get(f"{BASE_URL}/api/admin/invites", timeout=30)
        assert lr.status_code == 200
        assert any(i["code"] == code for i in lr.json()["invites"])

    def test_invite_bad_role_400(self, sa):
        r = sa.post(f"{BASE_URL}/api/admin/invites", json={"role": "root"}, timeout=30)
        assert r.status_code == 400, r.text[:300]

    def test_invite_forbidden_for_regular_user(self, usr):
        r = usr.post(f"{BASE_URL}/api/admin/invites", json={"role": "user"}, timeout=30)
        assert r.status_code == 403, r.text[:300]

    def test_invite_revoke(self, sa):
        r = sa.post(f"{BASE_URL}/api/admin/invites", json={"role": "user"}, timeout=30)
        code = r.json()["invite"]["code"]
        dr = sa.delete(f"{BASE_URL}/api/admin/invites/{code}", timeout=30)
        assert dr.status_code in (200, 204), dr.text[:200]
        lr = sa.get(f"{BASE_URL}/api/admin/invites", timeout=30)
        assert not any(i["code"] == code for i in lr.json()["invites"])


# ---------- regression ----------
class TestRegression:
    def test_admin_users(self, sa):
        r = sa.get(f"{BASE_URL}/api/admin/users", timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert isinstance(r.json().get("users"), list)

    def test_admin_companies(self, sa):
        r = sa.get(f"{BASE_URL}/api/admin/companies", timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert isinstance(r.json().get("companies"), list)

    def test_kb_list(self, sa):
        r = sa.get(f"{BASE_URL}/api/kb/list", timeout=30)
        assert r.status_code == 200, r.text[:300]

    def test_wallet_costs(self, usr):
        r = usr.get(f"{BASE_URL}/api/wallet/costs", timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert isinstance(r.json(), dict)

    def test_chat_create_and_fetch(self, usr):
        cr = usr.post(f"{BASE_URL}/api/chats", json={"mode": "faq"}, timeout=60)
        assert cr.status_code == 200, cr.text[:300]
        body = cr.json()
        chat_id = body.get("chat_id") or body.get("chat", {}).get("chat_id")
        assert chat_id
        gr = usr.get(f"{BASE_URL}/api/chats/{chat_id}", timeout=30)
        assert gr.status_code == 200, gr.text[:300]
        data = gr.json()
        assert "_id" not in str(data)[:2000] or "'_id'" not in str(data)
        usr.delete(f"{BASE_URL}/api/chats/{chat_id}", timeout=30)
