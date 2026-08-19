"""Iteration 3 — Usage Analytics dashboard (GET /api/analytics/summary)."""
import json
import os
from datetime import date, timedelta

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


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {SESSION_TOKEN}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def summary(client):
    r = client.get(f"{BASE_URL}/api/analytics/summary")
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- Auth ----------------
class TestAnalyticsAuth:
    def test_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/analytics/summary")
        assert r.status_code == 401, f"{r.status_code} {r.text[:300]}"

    def test_bad_token_401(self):
        r = requests.get(f"{BASE_URL}/api/analytics/summary",
                         headers={"Authorization": "Bearer not_a_real_token"})
        assert r.status_code == 401, f"{r.status_code} {r.text[:300]}"


# ---------------- Schema ----------------
class TestAnalyticsSchema:
    def test_top_level(self, summary):
        assert summary["window_days"] == 30
        assert isinstance(summary["wallet_balance"], float)
        assert '"_id"' not in json.dumps(summary)

    def test_totals(self, summary):
        t = summary["totals"]
        for k in ("spent", "messages", "reports_total", "reports_completed",
                  "faq_conversations", "topped_up"):
            assert k in t, t
        assert isinstance(t["spent"], float)
        assert isinstance(t["messages"], int)
        assert isinstance(t["reports_total"], int)
        assert isinstance(t["reports_completed"], int)
        assert isinstance(t["faq_conversations"], int)
        # NOTE: backend returns int 0 (not 0.0) when there are no top-ups in the window
        assert isinstance(t["topped_up"], (int, float))
        assert t["spent"] > 0, "seed events should produce spend"
        assert t["messages"] >= 45, t["messages"]
        assert t["reports_completed"] <= t["reports_total"]

    def test_kpis(self, summary):
        k = summary["kpis"]
        assert isinstance(k["avg_spend_per_report"], float)
        assert isinstance(k["completion_rate_pct"], float)
        assert 0 <= k["completion_rate_pct"] <= 100

    def test_daily_spend_30_days_ending_today(self, summary):
        ds = summary["daily_spend"]
        assert isinstance(ds, list)
        assert len(ds) == 30, len(ds)
        dates = [e["date"] for e in ds]
        expected = [(date.today() - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
        assert dates == expected, (dates[0], dates[-1])
        for e in ds:
            assert isinstance(e["amount"], (int, float))
            assert e["amount"] >= 0
        assert round(sum(e["amount"] for e in ds), 2) > 0

    def test_preferred_template(self, summary):
        p = summary["preferred_template"]
        assert isinstance(p, dict), p
        assert p["name"] == "Konut Değerleme Raporu", p
        for k in ("template_id", "name", "reports_completed", "messages", "spent"):
            assert k in p, p

    def test_template_breakdown_sorted_desc(self, summary):
        tb = summary["template_breakdown"]
        assert isinstance(tb, list) and len(tb) > 0
        spends = [t["spent"] for t in tb]
        assert spends == sorted(spends, reverse=True), spends
        for t in tb:
            for k in ("template_id", "name", "messages", "spent", "reports_total", "reports_completed"):
                assert k in t, t
        names = [t["name"] for t in tb]
        assert "Konut Değerleme Raporu" in names, names

    def test_totals_match_breakdown(self, summary):
        tb = summary["template_breakdown"]
        assert round(sum(t["spent"] for t in tb), 2) == pytest.approx(summary["totals"]["spent"], abs=0.05)
        assert sum(t["messages"] for t in tb) == summary["totals"]["messages"]


# ---------------- Live increment (1 short LLM call) ----------------
class TestAnalyticsIncrement:
    def test_faq_message_increments_analytics(self, client):
        before = client.get(f"{BASE_URL}/api/analytics/summary")
        assert before.status_code == 200, before.text
        b = before.json()
        faq_before = next((t for t in b["template_breakdown"] if t["template_id"] == "faq"), None)
        faq_spent_before = faq_before["spent"] if faq_before else 0.0

        c = client.post(f"{BASE_URL}/api/chats", json={"mode": "faq"})
        assert c.status_code == 200, c.text
        chat_id = c.json().get("chat_id") or c.json()["chat"]["chat_id"]

        r = client.post(f"{BASE_URL}/api/chats/{chat_id}/message",
                        json={"content": "Tek kelimeyle: emlak nedir?"}, stream=True, timeout=180)
        assert r.status_code == 200, r.text
        types = []
        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                types.append(json.loads(line[6:])["type"])
        assert "error" not in types, types
        assert types[-1] == "done", types

        after = client.get(f"{BASE_URL}/api/analytics/summary")
        assert after.status_code == 200, after.text
        a = after.json()
        assert a["totals"]["spent"] == pytest.approx(round(b["totals"]["spent"] + 2.0, 2), abs=0.01), \
            (b["totals"]["spent"], a["totals"]["spent"])
        assert a["totals"]["messages"] == b["totals"]["messages"] + 1
        assert a["totals"]["faq_conversations"] == b["totals"]["faq_conversations"] + 1

        faq_after = next((t for t in a["template_breakdown"] if t["template_id"] == "faq"), None)
        assert faq_after is not None, a["template_breakdown"]
        assert faq_after["spent"] == pytest.approx(round(faq_spent_before + 2.0, 2), abs=0.01)

        today = date.today().isoformat()
        d_before = next(e["amount"] for e in b["daily_spend"] if e["date"] == today)
        d_after = next(e["amount"] for e in a["daily_spend"] if e["date"] == today)
        assert d_after == pytest.approx(round(d_before + 2.0, 2), abs=0.01)

        client.delete(f"{BASE_URL}/api/chats/{chat_id}")
