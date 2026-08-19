"""Backend regression tests — v2 wallet / Stripe / SSE streaming features."""
import json
import os
import re
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

SESSION_TOKEN = "test_session_seed_001"
USER_ID = "test-user-seed-001"


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {SESSION_TOKEN}", "Content-Type": "application/json"})
    return s


def _mongo(js):
    import subprocess
    return subprocess.run(["mongosh", "--quiet", "--eval", js], capture_output=True, text=True)


def _set_balance(val):
    r = _mongo(f"db.getSiblingDB('test_database').users.updateOne({{user_id:'{USER_ID}'}},{{$set:{{wallet_balance:{val}}}}})")
    assert "matchedCount" in r.stdout or r.returncode == 0, r.stderr


# ---------------- Wallet metadata endpoints ----------------
class TestWalletMeta:
    def test_packages(self, client):
        r = client.get(f"{BASE_URL}/api/wallet/packages")
        assert r.status_code == 200, r.text
        data = r.json()
        pkgs = data["packages"] if isinstance(data, dict) and "packages" in data else data
        assert len(pkgs) == 5
        ids = [p["id"] for p in pkgs]
        assert ids == ["topup_100", "topup_250", "topup_500", "topup_1000", "topup_2500"]
        for p in pkgs:
            assert isinstance(p["amount_try"], float)
            assert isinstance(p["bonus_try"], float)
            assert p["label"]

    def test_costs(self, client):
        r = client.get(f"{BASE_URL}/api/wallet/costs")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["faq"] == 2.0
        assert len(data["templates"]) == 4
        costs = {t["id"]: t["cost_per_message"] for t in data["templates"]}
        assert costs == {"konut": 4.0, "ticari": 6.0, "arsa": 3.0, "endustriyel": 8.0}, costs


# ---------------- Auth / migration ----------------
class TestAuthMigration:
    def test_me_has_wallet_balance(self, client):
        r = client.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200, r.text
        u = r.json()
        assert "wallet_balance" in u
        assert isinstance(u["wallet_balance"], float)
        assert "credits" not in u
        assert u["user_id"] == USER_ID

    def test_old_credits_endpoints_removed(self, client):
        r1 = client.get(f"{BASE_URL}/api/credits/packages")
        r2 = client.post(f"{BASE_URL}/api/credits/purchase", json={"package_id": "starter"})
        assert r1.status_code == 404, r1.status_code
        assert r2.status_code == 404, r2.status_code


# ---------------- Stripe checkout ----------------
class TestStripe:
    session_id = None

    def test_checkout(self, client):
        r = client.post(f"{BASE_URL}/api/wallet/checkout",
                        json={"package_id": "topup_100", "origin_url": BASE_URL})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["url"].startswith("https://checkout.stripe.com/") if "url" in d else \
            d["checkout_url"].startswith("https://checkout.stripe.com/"), d
        sid = d.get("session_id")
        assert sid and sid.startswith("cs_test_"), d
        TestStripe.session_id = sid

    def test_checkout_invalid_package(self, client):
        r = client.post(f"{BASE_URL}/api/wallet/checkout",
                        json={"package_id": "nope", "origin_url": BASE_URL})
        assert r.status_code in (400, 404), r.status_code

    def test_status_no_auth(self):
        assert TestStripe.session_id, "checkout must run first"
        r = requests.get(f"{BASE_URL}/api/wallet/status/{TestStripe.session_id}")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("status", "payment_status", "credited"):
            assert k in d, d
        assert d["credited"] is False
        assert d["payment_status"] in ("unpaid", "no_payment_required", "paid")

    def test_webhook_empty_body_400(self):
        r = requests.post(f"{BASE_URL}/api/webhook/stripe", data=b"")
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"


# ---------------- SSE streaming ----------------
class TestStreaming:
    def test_faq_stream_and_charge(self, client):
        _set_balance(100)
        me = client.get(f"{BASE_URL}/api/auth/me").json()
        start = me["wallet_balance"]

        c = client.post(f"{BASE_URL}/api/chats", json={"mode": "faq"})
        assert c.status_code == 200, c.text
        chat_id = c.json().get("chat_id") or c.json()["chat"]["chat_id"]

        after_create = client.get(f"{BASE_URL}/api/auth/me").json()["wallet_balance"]
        assert after_create == start, f"chat create should be free: {start} -> {after_create}"

        r = client.post(f"{BASE_URL}/api/chats/{chat_id}/message",
                        json={"content": "Cap rate nedir? Tek cümle."}, stream=True, timeout=120)
        assert r.status_code == 200, r.text
        assert "text/event-stream" in r.headers.get("Content-Type", ""), r.headers

        events = []
        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                events.append(json.loads(line[6:]))
        types = [e["type"] for e in events]
        assert types.count("user_message") == 1, types
        assert types.count("delta") >= 1, types
        assert types[-1] == "done", types
        assert "error" not in types, [e for e in events if e["type"] == "error"]

        done = events[-1]
        assert done["assistant_message"]["role"] == "assistant"
        assert done["assistant_message"]["content"].strip()
        assert done["chat"]["chat_id"] == chat_id
        assert "_id" not in done["chat"]
        assert done["cost_charged"] == 2.0
        assert isinstance(done["low_balance_warning"], bool)
        assert done["wallet_balance"] == round(start - 2.0, 2), (start, done["wallet_balance"])

        # persisted
        final = client.get(f"{BASE_URL}/api/auth/me").json()["wallet_balance"]
        assert final == round(start - 2.0, 2), final

        client.delete(f"{BASE_URL}/api/chats/{chat_id}")

    def test_insufficient_balance_402(self, client):
        c = client.post(f"{BASE_URL}/api/chats", json={"mode": "faq"})
        chat_id = c.json().get("chat_id") or c.json()["chat"]["chat_id"]
        _set_balance(0.5)
        try:
            r = client.post(f"{BASE_URL}/api/chats/{chat_id}/message", json={"content": "test"}, timeout=60)
            assert r.status_code == 402, f"{r.status_code} {r.text[:300]}"
            assert "insufficient_balance" in r.text
        finally:
            _set_balance(100)
            client.delete(f"{BASE_URL}/api/chats/{chat_id}")

    def test_message_unknown_chat_404(self, client):
        r = client.post(f"{BASE_URL}/api/chats/nope_xyz/message", json={"content": "x"}, timeout=60)
        assert r.status_code == 404, r.status_code
