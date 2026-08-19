"""Tests for KırCan Report AI: Admin/Super-Admin RBAC, Knowledge Base, Invites, Profile."""
import os
import uuid
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
SUPER_UID = "user_grelligram_seed"
USER_UID = "test-user-seed-001"


backend_env = dotenv_values("/app/backend/.env")


def _mongo():
    from pymongo import MongoClient
    mc = MongoClient(backend_env["MONGO_URL"])
    return mc[backend_env["DB_NAME"]]


def _make_temp_user(prefix="TEST_tmp"):
    """Insert a temp user + session directly, return (user_id, token)."""
    from datetime import datetime, timedelta, timezone as tz
    dbm = _mongo()
    uid = f"{prefix}_{uuid.uuid4().hex[:8]}"
    token = f"tok_{uuid.uuid4().hex[:16]}"
    dbm.users.insert_one({
        "user_id": uid, "email": f"{uid}@test.com".lower(), "name": "TEST Temp",
        "wallet_balance": 10.0, "role": "user", "blocked": False, "company_id": None,
        "created_at": datetime.now(tz.utc),
    })
    dbm.user_sessions.insert_one({
        "user_id": uid, "session_token": token,
        "expires_at": datetime.now(tz.utc) + timedelta(days=1),
        "created_at": datetime.now(tz.utc),
    })
    return uid, token


def _purge_temp(uid):
    dbm = _mongo()
    dbm.users.delete_many({"user_id": uid})
    dbm.user_sessions.delete_many({"user_id": uid})


def client(token=None):
    s = requests.Session()
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="session")
def sup():
    return client(SUPER_TOKEN)


@pytest.fixture(scope="session")
def usr():
    return client(USER_TOKEN)


@pytest.fixture(scope="session")
def anon():
    return client()


# ---------------- Auth / role backfill ----------------
class TestAuth:
    def test_super_admin_me(self, sup):
        r = sup.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["email"] == "grelligram@gmail.com"
        assert d["role"] == "super_admin"
        assert d["blocked"] is False
        assert "_id" not in d

    def test_user_me(self, usr):
        r = usr.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["role"] == "user"
        assert d["email"] == "test.valuer@example.com"

    def test_unauth_me(self, anon):
        r = anon.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 401


# ---------------- Admin: users list/detail ----------------
class TestAdminUsers:
    def test_list_users_super(self, sup):
        r = sup.get(f"{BASE_URL}/api/admin/users")
        assert r.status_code == 200, r.text
        users = r.json()["users"]
        assert any(u["user_id"] == USER_UID for u in users)
        u = [x for x in users if x["user_id"] == USER_UID][0]
        assert "chat_count" in u and "total_spent" in u
        assert "_id" not in u

    def test_list_users_forbidden_for_user(self, usr):
        r = usr.get(f"{BASE_URL}/api/admin/users")
        assert r.status_code == 403, r.text

    def test_user_detail(self, sup):
        r = sup.get(f"{BASE_URL}/api/admin/users/{USER_UID}")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["user"]["user_id"] == USER_UID
        assert isinstance(d["chats"], list)
        assert isinstance(d["wallet_transactions"], list)

    def test_user_detail_404(self, sup):
        r = sup.get(f"{BASE_URL}/api/admin/users/does-not-exist")
        assert r.status_code == 404

    def test_system_summary(self, sup):
        r = sup.get(f"{BASE_URL}/api/admin/system/summary")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("total_users", "total_chats", "total_spent", "wallet_balance_sum",
                  "company_budget_sum", "company_count"):
            assert k in d
        assert d["total_users"] >= 2

    def test_summary_forbidden_for_user(self, usr):
        assert usr.get(f"{BASE_URL}/api/admin/system/summary").status_code == 403


# ---------------- Wallet topup ----------------
class TestWalletTopup:
    def test_topup_increases_balance(self, sup, usr):
        before = usr.get(f"{BASE_URL}/api/auth/me").json()["wallet_balance"]
        r = sup.post(f"{BASE_URL}/api/admin/users/{USER_UID}/wallet/topup",
                     json={"amount": 25.5, "note": "TEST_topup"})
        assert r.status_code == 200, r.text
        assert r.json()["user"]["wallet_balance"] == pytest.approx(before + 25.5)
        # verify persistence via /auth/me
        after = usr.get(f"{BASE_URL}/api/auth/me").json()["wallet_balance"]
        assert after == pytest.approx(before + 25.5)
        # ledger recorded
        det = sup.get(f"{BASE_URL}/api/admin/users/{USER_UID}").json()
        assert any(t.get("note") == "TEST_topup" for t in det["wallet_transactions"])
        # revert
        sup.post(f"{BASE_URL}/api/admin/users/{USER_UID}/wallet/topup", json={"amount": 0.01})

    def test_topup_invalid_amount(self, sup):
        r = sup.post(f"{BASE_URL}/api/admin/users/{USER_UID}/wallet/topup", json={"amount": -5})
        assert r.status_code == 400
        r2 = sup.post(f"{BASE_URL}/api/admin/users/{USER_UID}/wallet/topup", json={"amount": "abc"})
        assert r2.status_code == 400

    def test_topup_forbidden_for_user(self, usr):
        r = usr.post(f"{BASE_URL}/api/admin/users/{SUPER_UID}/wallet/topup", json={"amount": 10})
        assert r.status_code == 403


# ---------------- Companies ----------------
class TestCompanies:
    company_id = None

    def test_create_company(self, sup):
        r = sup.post(f"{BASE_URL}/api/admin/companies", json={"name": "TEST_Sirket A.Ş."})
        assert r.status_code == 200, r.text
        c = r.json()["company"]
        assert c["name"] == "TEST_Sirket A.Ş."
        assert c["budget_balance"] == 0.0
        assert "_id" not in c
        TestCompanies.company_id = c["company_id"]

    def test_create_company_empty_name(self, sup):
        assert sup.post(f"{BASE_URL}/api/admin/companies", json={"name": "  "}).status_code == 400

    def test_create_company_forbidden(self, usr):
        assert usr.post(f"{BASE_URL}/api/admin/companies", json={"name": "X"}).status_code == 403

    def test_budget_topup(self, sup):
        cid = TestCompanies.company_id
        assert cid, "company not created"
        r = sup.post(f"{BASE_URL}/api/admin/companies/{cid}/budget/topup", json={"amount": 100})
        assert r.status_code == 200, r.text
        assert r.json()["company"]["budget_balance"] == pytest.approx(100)
        lst = sup.get(f"{BASE_URL}/api/admin/companies").json()["companies"]
        found = [c for c in lst if c["company_id"] == cid][0]
        assert found["budget_balance"] == pytest.approx(100)
        assert "user_count" in found

    def test_budget_topup_bad_company(self, sup):
        r = sup.post(f"{BASE_URL}/api/admin/companies/nope/budget/topup", json={"amount": 10})
        assert r.status_code == 404

    def test_list_companies_forbidden(self, usr):
        assert usr.get(f"{BASE_URL}/api/admin/companies").status_code == 403


# ---------------- Roles ----------------
class TestRoles:
    def test_set_role_admin_autocreates_company(self, sup, usr):
        r = sup.post(f"{BASE_URL}/api/admin/users/{USER_UID}/role", json={"role": "admin"})
        assert r.status_code == 200, r.text
        u = r.json()["user"]
        assert u["role"] == "admin"
        assert u["company_id"], "admin should get auto-created company"
        cid = u["company_id"]
        comps = sup.get(f"{BASE_URL}/api/admin/companies").json()["companies"]
        assert any(c["company_id"] == cid for c in comps)
        # admin can now list users scoped to company
        r2 = usr.get(f"{BASE_URL}/api/admin/users")
        assert r2.status_code == 200, r2.text
        assert all(x.get("company_id") == cid for x in r2.json()["users"])
        # revert
        rev = sup.post(f"{BASE_URL}/api/admin/users/{USER_UID}/role", json={"role": "user"})
        assert rev.status_code == 200
        assert rev.json()["user"]["role"] == "user"

    def test_invalid_role(self, sup):
        r = sup.post(f"{BASE_URL}/api/admin/users/{USER_UID}/role", json={"role": "god"})
        assert r.status_code == 400

    def test_role_change_forbidden_for_user(self, usr):
        r = usr.post(f"{BASE_URL}/api/admin/users/{SUPER_UID}/role", json={"role": "user"})
        assert r.status_code == 403


# ---------------- Block / Delete ----------------
class TestBlockDelete:
    def test_block_then_unblock(self, sup):
        uid, token = _make_temp_user("TEST_blk")
        try:
            tmp = client(token)
            assert tmp.get(f"{BASE_URL}/api/auth/me").status_code == 200
            r = sup.post(f"{BASE_URL}/api/admin/users/{uid}/block", json={"blocked": True})
            assert r.status_code == 200, r.text
            assert r.json()["blocked"] is True
            # blocked user's session is invalidated -> 401 (sessions deleted) or 403
            me = client(token).get(f"{BASE_URL}/api/auth/me")
            assert me.status_code in (401, 403), me.status_code
            # verify flag persisted
            det = sup.get(f"{BASE_URL}/api/admin/users/{uid}").json()["user"]
            assert det["blocked"] is True
            r2 = sup.post(f"{BASE_URL}/api/admin/users/{uid}/block", json={"blocked": False})
            assert r2.status_code == 200
            assert r2.json()["blocked"] is False
            det2 = sup.get(f"{BASE_URL}/api/admin/users/{uid}").json()["user"]
            assert det2["blocked"] is False
        finally:
            _purge_temp(uid)

    def test_block_forbidden_for_user(self, usr):
        assert usr.post(f"{BASE_URL}/api/admin/users/{SUPER_UID}/block",
                        json={"blocked": True}).status_code == 403

    def test_cannot_delete_self(self, sup):
        assert sup.delete(f"{BASE_URL}/api/admin/users/{SUPER_UID}").status_code == 400

    def test_delete_temp_user(self, sup):
        uid, _ = _make_temp_user("TEST_del")
        r = sup.delete(f"{BASE_URL}/api/admin/users/{uid}")
        assert r.status_code == 200, r.text
        assert sup.get(f"{BASE_URL}/api/admin/users/{uid}").status_code == 404
        _purge_temp(uid)

    def test_delete_forbidden_for_user(self, usr):
        assert usr.delete(f"{BASE_URL}/api/admin/users/{SUPER_UID}").status_code == 403


# ---------------- Invites ----------------
class TestInvites:
    code = None

    def test_create_invite(self, sup):
        r = sup.post(f"{BASE_URL}/api/admin/invites", json={"role": "user", "email": "TEST_invitee@example.com"})
        assert r.status_code == 200, r.text
        inv = r.json()["invite"]
        assert inv["role"] == "user"
        assert inv["used"] is False
        assert inv["code"].startswith("inv_")
        assert "_id" not in inv
        TestInvites.code = inv["code"]

    def test_public_invite_lookup(self, anon):
        r = anon.get(f"{BASE_URL}/api/invites/{TestInvites.code}")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("role") == "user"

    def test_public_invite_invalid(self, anon):
        r = anon.get(f"{BASE_URL}/api/invites/inv_nonexistent")
        assert r.status_code in (404, 400), r.status_code

    def test_invalid_role_invite(self, sup):
        assert sup.post(f"{BASE_URL}/api/admin/invites", json={"role": "super_admin"}).status_code == 400

    def test_list_invites(self, sup):
        r = sup.get(f"{BASE_URL}/api/admin/invites")
        assert r.status_code == 200
        assert any(i["code"] == TestInvites.code for i in r.json()["invites"])

    def test_invite_forbidden_for_user(self, usr):
        assert usr.post(f"{BASE_URL}/api/admin/invites", json={"role": "user"}).status_code == 403
        assert usr.get(f"{BASE_URL}/api/admin/invites").status_code == 403

    def test_revoke_invite(self, sup):
        r = sup.delete(f"{BASE_URL}/api/admin/invites/{TestInvites.code}")
        assert r.status_code == 200
        assert sup.delete(f"{BASE_URL}/api/admin/invites/{TestInvites.code}").status_code == 404


# ---------------- Knowledge Base ----------------
class TestKnowledgeBase:
    doc_id = None

    def test_upload_txt_global(self, sup):
        files = {"file": ("TEST_kb.txt", b"Gayrimenkul degerleme kurallari: emsal analizi zorunludur.", "text/plain")}
        r = sup.post(f"{BASE_URL}/api/kb/upload", files=files,
                     data={"scope": "global", "title": "TEST_KB Dok"})
        assert r.status_code == 200, r.text
        d = r.json()["document"]
        assert d["scope"] == "global"
        assert d["title"] == "TEST_KB Dok"
        assert d["size"] > 0
        assert "text_content" not in d
        assert "_id" not in d
        TestKnowledgeBase.doc_id = d["doc_id"]

    def test_list_shows_doc(self, sup, usr):
        r = sup.get(f"{BASE_URL}/api/kb/list")
        assert r.status_code == 200, r.text
        assert any(d["doc_id"] == TestKnowledgeBase.doc_id for d in r.json()["documents"])
        # global doc visible to regular user too
        r2 = usr.get(f"{BASE_URL}/api/kb/list")
        assert r2.status_code == 200, r2.text
        assert any(d["doc_id"] == TestKnowledgeBase.doc_id for d in r2.json()["documents"])

    def test_upload_rejects_bad_extension(self, sup):
        files = {"file": ("bad.exe", b"xx", "application/octet-stream")}
        r = sup.post(f"{BASE_URL}/api/kb/upload", files=files, data={"scope": "global"})
        assert r.status_code == 400, r.text

    def test_upload_invalid_scope(self, sup):
        files = {"file": ("TEST_x.txt", b"hello", "text/plain")}
        r = sup.post(f"{BASE_URL}/api/kb/upload", files=files, data={"scope": "weird"})
        assert r.status_code == 400

    def test_upload_forbidden_for_user(self, usr):
        files = {"file": ("TEST_u.txt", b"hello", "text/plain")}
        r = usr.post(f"{BASE_URL}/api/kb/upload", files=files, data={"scope": "global"})
        assert r.status_code == 403, r.text

    def test_delete_forbidden_for_user(self, usr):
        r = usr.delete(f"{BASE_URL}/api/kb/{TestKnowledgeBase.doc_id}")
        assert r.status_code == 403, r.text

    def test_delete_doc(self, sup):
        r = sup.delete(f"{BASE_URL}/api/kb/{TestKnowledgeBase.doc_id}")
        assert r.status_code == 200, r.text
        docs = sup.get(f"{BASE_URL}/api/kb/list").json()["documents"]
        assert not any(d["doc_id"] == TestKnowledgeBase.doc_id for d in docs)
        assert sup.delete(f"{BASE_URL}/api/kb/{TestKnowledgeBase.doc_id}").status_code == 404


# ---------------- Profile update ----------------
class TestProfile:
    def test_update_name(self, usr):
        original = usr.get(f"{BASE_URL}/api/auth/me").json()["name"]
        r = usr.patch(f"{BASE_URL}/api/auth/me", json={"name": "TEST_Updated Name"})
        assert r.status_code == 200, r.text
        assert usr.get(f"{BASE_URL}/api/auth/me").json()["name"] == "TEST_Updated Name"
        # revert
        usr.patch(f"{BASE_URL}/api/auth/me", json={"name": original})
        assert usr.get(f"{BASE_URL}/api/auth/me").json()["name"] == original

    def test_role_not_escalatable_via_profile(self, usr):
        r = usr.patch(f"{BASE_URL}/api/auth/me", json={"role": "super_admin"})
        assert r.status_code in (200, 400, 422)
        assert usr.get(f"{BASE_URL}/api/auth/me").json()["role"] == "user"


# ---------------- Regression: wallet costs / chat / templates ----------------
class TestRegression:
    def test_wallet_costs(self, usr):
        r = usr.get(f"{BASE_URL}/api/wallet/costs")
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), (dict, list))

    def test_templates_list(self, usr):
        r = usr.get(f"{BASE_URL}/api/templates")
        assert r.status_code == 200, r.text

    def test_faq_chat_flow(self, usr):
        r = usr.post(f"{BASE_URL}/api/chats", json={"mode": "faq", "title": "TEST_FAQ"})
        assert r.status_code in (200, 201), r.text
        chat = r.json()["chat"]
        chat_id = chat.get("chat_id")
        assert chat_id
        m = usr.post(f"{BASE_URL}/api/chats/{chat_id}/message",
                     json={"content": "Emsal analizi nedir?"}, timeout=180, stream=True)
        assert m.status_code == 200, m.text[:600]
        body = b""
        for chunk in m.iter_content(chunk_size=1024):
            body += chunk
            if len(body) > 4000:
                break
        m.close()
        assert b"delta" in body or b"done" in body, body[:400]
        usr.delete(f"{BASE_URL}/api/chats/{chat_id}")
