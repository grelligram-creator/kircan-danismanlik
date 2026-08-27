"""Phase 1b + Phase 2 backend tests.

Covers:
  - POST /api/chats/{id}/autofill  (Claude Vision autofill, wallet reconciliation, usage_events)
  - PATCH /api/chats/{id}/fields   (merge / clear)
  - Regression: POST /api/chats/{id}/message SSE  (real token counting, max_tokens cap, scope guard)

NOTE: real LLM calls are limited to 2 for the whole module (1 vision + 1 SSE).
"""
import io
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

backend_env = dotenv_values("/app/backend/.env")
MONGO_URL = os.environ.get("MONGO_URL") or backend_env.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or backend_env.get("DB_NAME")
USD_TRY = float(os.environ.get("USD_TRY_RATE") or backend_env.get("USD_TRY_RATE") or "42")

SUPER_TOKEN = "test_super_admin_token"
USER_TOKEN = "test_session_seed_001"
POOR_TOKEN = "TEST_poor_session_token"
POOR_USER_ID = "TEST_poor_user_001"


# ---------------------------------------------------------------- fixtures
@pytest.fixture(scope="session")
def mongo():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="session")
def admin():
    s = requests.Session()
    s.cookies.set("session_token", SUPER_TOKEN)
    return s


@pytest.fixture(scope="session")
def poor_client(mongo):
    """A seeded user with 0 TL wallet, for the 402 insufficient_balance path."""
    mongo.users.update_one(
        {"user_id": POOR_USER_ID},
        {"$set": {
            "user_id": POOR_USER_ID, "email": "TEST_poor@example.test",
            "name": "TEST Poor User", "wallet_balance": 0.0, "role": "user",
            "blocked": False, "company_id": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    mongo.user_sessions.update_one(
        {"session_token": POOR_TOKEN},
        {"$set": {"session_token": POOR_TOKEN, "user_id": POOR_USER_ID,
                  "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
                  "created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    s = requests.Session()
    s.cookies.set("session_token", POOR_TOKEN)
    yield s
    mongo.users.delete_one({"user_id": POOR_USER_ID})
    mongo.user_sessions.delete_one({"session_token": POOR_TOKEN})
    mongo.chats.delete_many({"user_id": POOR_USER_ID})


@pytest.fixture(scope="session")
def state():
    """Shared IDs created during the module, cleaned up at the end."""
    return {"chats": [], "uploads": []}


@pytest.fixture(scope="session", autouse=True)
def cleanup(state, mongo, admin):
    yield
    for cid in state["chats"]:
        admin.delete(f"{API}/chats/{cid}")
        mongo.chats.delete_many({"chat_id": cid})
        mongo.messages.delete_many({"chat_id": cid})
        mongo.usage_events.delete_many({"chat_id": cid})
    for uid in state["uploads"]:
        mongo.uploads.delete_many({"upload_id": uid})


@pytest.fixture(scope="session")
def konut_chat(admin, state):
    r = admin.post(f"{API}/chats", json={"mode": "report", "template_id": "konut"})
    assert r.status_code == 200, r.text
    cid = r.json()["chat"]["chat_id"]
    state["chats"].append(cid)
    return cid


def _make_tapu_png() -> bytes:
    """Render a small tapu-like image with Turkish text."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (760, 420), "white")
    d = ImageDraw.Draw(img)
    font = None
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if Path(p).exists():
            font = ImageFont.truetype(p, 22)
            break
    lines = [
        "TAPU KAYIT BELGESI",
        "Il: Ankara   Ilce: Cankaya",
        "Ada / Parsel No: 1234 / 56",
        "Acik Adres: Kizilay Mah. Ataturk Cad. No 12 D:5 Cankaya/Ankara",
        "Brut Alan (m2): 145",
        "Net Alan (m2): 128",
        "Oda Sayisi: 3+1",
        "Bina Yasi: 12",
        "Bulundugu Kat: 4",
        "Isitma Sistemi: Dogalgaz Kombi",
    ]
    y = 20
    for ln in lines:
        d.text((20, y), ln, fill="black", font=font)
        y += 38
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="session")
def tapu_upload(admin, state):
    files = {"file": ("TEST_tapu.png", _make_tapu_png(), "image/png")}
    r = admin.post(f"{API}/uploads", files=files)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "_id" not in data
    state["uploads"].append(data["upload_id"])
    return data["upload_id"]


@pytest.fixture(scope="session")
def txt_upload(admin, state):
    files = {"file": ("TEST_notes.txt", b"bu bir metin dosyasidir", "text/plain")}
    r = admin.post(f"{API}/uploads", files=files)
    assert r.status_code == 200, r.text
    state["uploads"].append(r.json()["upload_id"])
    return r.json()["upload_id"]


def _balance(session) -> float:
    r = session.get(f"{API}/auth/me")
    assert r.status_code == 200, r.text
    return float(r.json()["wallet_balance"])


# ---------------------------------------------------------------- health / auth
class TestHealthAndAuth:
    def test_super_admin_session(self, admin):
        r = admin.get(f"{API}/auth/me")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["email"] == "grelligram@gmail.com"
        assert d["role"] == "super_admin"
        assert d["wallet_balance"] >= 5.0

    def test_message_route_registered(self):
        """Regression guard: the SSE chat endpoint must exist in the OpenAPI schema."""
        probe = requests.post(f"{API}/chats/does_not_exist/message", json={"content": "x"})
        assert probe.status_code != 405, "POST /api/chats/{id}/message is NOT registered (405)"
        assert probe.status_code in (401, 403, 404), probe.status_code


# ---------------------------------------------------------------- autofill validation
class TestAutofillValidation:
    def test_unknown_chat_404(self, admin):
        r = admin.post(f"{API}/chats/chat_nope/autofill", json={"attachment_ids": ["x"]})
        assert r.status_code == 404, r.text

    def test_empty_attachment_ids_400(self, admin, konut_chat):
        before = _balance(admin)
        r = admin.post(f"{API}/chats/{konut_chat}/autofill", json={"attachment_ids": []})
        assert r.status_code == 400, r.text
        assert "ek dosya" in r.json()["detail"].lower()
        assert _balance(admin) == pytest.approx(before, abs=0.01), "wallet must not be charged on 400"

    def test_missing_attachment_ids_key_400(self, admin, konut_chat):
        r = admin.post(f"{API}/chats/{konut_chat}/autofill", json={})
        assert r.status_code == 400, r.text

    def test_non_image_attachment_400_and_refund(self, admin, konut_chat, txt_upload):
        before = _balance(admin)
        r = admin.post(f"{API}/chats/{konut_chat}/autofill", json={"attachment_ids": [txt_upload]})
        assert r.status_code == 400, r.text
        assert "Analiz edilebilir" in r.json()["detail"]
        after = _balance(admin)
        assert after == pytest.approx(before, abs=0.01), f"5 TL hold not refunded: {before} -> {after}"

    def test_unknown_attachment_id_400_and_refund(self, admin, konut_chat):
        before = _balance(admin)
        r = admin.post(f"{API}/chats/{konut_chat}/autofill", json={"attachment_ids": ["up_doesnotexist"]})
        assert r.status_code == 400, r.text
        assert _balance(admin) == pytest.approx(before, abs=0.01)

    def test_insufficient_balance_402(self, poor_client, tapu_upload):
        r = poor_client.post(f"{API}/chats", json={"mode": "report", "template_id": "konut"})
        assert r.status_code == 200, r.text
        cid = r.json()["chat"]["chat_id"]
        r2 = poor_client.post(f"{API}/chats/{cid}/autofill", json={"attachment_ids": [tapu_upload]})
        assert r2.status_code == 402, r2.text
        detail = r2.json()["detail"]
        assert detail["error"] == "insufficient_balance"
        assert detail["required"] == 5.0
        assert _balance(poor_client) == pytest.approx(0.0, abs=0.01)

    def test_other_users_attachment_not_readable(self, poor_client, mongo, tapu_upload):
        """Attachment owned by super-admin must not be usable by another user."""
        mongo.users.update_one({"user_id": POOR_USER_ID}, {"$set": {"wallet_balance": 20.0}})
        r = poor_client.post(f"{API}/chats", json={"mode": "report", "template_id": "konut"})
        cid = r.json()["chat"]["chat_id"]
        r2 = poor_client.post(f"{API}/chats/{cid}/autofill", json={"attachment_ids": [tapu_upload]})
        assert r2.status_code == 400, r2.text
        assert _balance(poor_client) == pytest.approx(20.0, abs=0.01)
        mongo.users.update_one({"user_id": POOR_USER_ID}, {"$set": {"wallet_balance": 0.0}})

    def test_unauthenticated_401(self, konut_chat):
        r = requests.post(f"{API}/chats/{konut_chat}/autofill", json={"attachment_ids": ["x"]})
        assert r.status_code in (401, 403), r.status_code


# ---------------------------------------------------------------- autofill: 1 REAL vision call
class TestAutofillVision:
    result = {}

    def test_vision_autofill_success(self, admin, konut_chat, tapu_upload, mongo, state):
        before = _balance(admin)
        t0 = time.time()
        r = admin.post(f"{API}/chats/{konut_chat}/autofill",
                       json={"attachment_ids": [tapu_upload]}, timeout=240)
        elapsed = time.time() - t0
        assert r.status_code == 200, f"{r.status_code}: {r.text[:800]}"
        d = r.json()
        TestAutofillVision.result = d
        print(f"\n[autofill] {elapsed:.1f}s -> {json.dumps(d, ensure_ascii=False)[:900]}")

        # structure
        for key in ("fields", "duplicates", "out_of_scope", "notes", "tokens", "cost_try",
                    "wallet_balance", "files_analyzed"):
            assert key in d, f"missing key {key}"
        assert d["success"] is True
        assert d["files_analyzed"] == 1
        assert isinstance(d["fields"], dict)
        assert isinstance(d["duplicates"], list)
        assert isinstance(d["out_of_scope"], list)

        # real token counting
        assert d["tokens"]["input"] > 0, "input tokens not reported by Vision call"
        assert d["tokens"]["output"] > 0, "output tokens not reported by Vision call"

        # extraction quality (soft): at least a couple of konut fields resolved
        assert len(d["fields"]) >= 3, f"too few fields extracted: {d['fields']}"

        # wallet decremented by exactly cost_try
        after = _balance(admin)
        assert after == pytest.approx(before - d["cost_try"], abs=0.02), \
            f"wallet {before} -> {after}, cost_try={d['cost_try']}"
        assert after >= 0, "wallet went negative"

    def test_wallet_reconciliation(self, admin, mongo):
        d = TestAutofillVision.result
        if not d:
            pytest.skip("vision call did not succeed")
        assert d["cost_try"] >= 1.0, "minimum 1 TL charge not applied"
        # wallet_balance returned must match /auth/me
        live = _balance(admin)
        assert live == pytest.approx(d["wallet_balance"], abs=0.02), \
            f"returned wallet_balance {d['wallet_balance']} != live {live}"

    def test_usage_event_written(self, mongo, konut_chat):
        d = TestAutofillVision.result
        if not d:
            pytest.skip("vision call did not succeed")
        ev = mongo.usage_events.find_one({"chat_id": konut_chat, "mode": "autofill"},
                                         sort=[("created_at", -1)])
        assert ev is not None, "no usage_events row with mode='autofill'"
        assert ev["input_tokens"] == d["tokens"]["input"]
        assert ev["output_tokens"] == d["tokens"]["output"]
        assert ev["actual_ai_cost_try"] > 0
        assert ev["cost"] == pytest.approx(d["cost_try"], abs=0.01)
        assert ev["file_count"] == 1
        # markup formula check: charged == max(actual*1.30, 1.0)
        expected = max(round(ev["actual_ai_cost_try"] * 1.30, 2), 1.0)
        assert ev["cost"] == pytest.approx(expected, abs=0.02), \
            f"charged {ev['cost']} != expected {expected} (actual_try={ev['actual_ai_cost_try']})"

    def test_temp_files_cleaned(self, konut_chat):
        tmp = Path("/app/backend/generated_reports") / konut_chat / "_autofill"
        leftovers = list(tmp.glob("*")) if tmp.exists() else []
        assert not leftovers, f"temp autofill files not cleaned: {leftovers}"


# ---------------------------------------------------------------- iteration-11 safeguards
def _make_tapu_pdf() -> bytes:
    """Small text PDF (pypdf-extractable) with tapu-like content."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for ln in [
        "TAPU KAYIT BELGESI (PDF)",
        "Il: Izmir   Ilce: Bornova",
        "Ada / Parsel No: 4321 / 9",
        "Acik Adres: Kazimdirik Mah. Ankara Cad. No 44 D:3 Bornova/Izmir",
        "Brut Alan (m2): 110",
        "Net Alan (m2): 96",
        "Oda Sayisi: 2+1",
        "Bina Yasi: 7",
        "Bulundugu Kat: 2",
        "Isitma Sistemi: Merkezi Sistem",
    ]:
        c.drawString(50, y, ln)
        y -= 26
    c.showPage()
    c.save()
    return buf.getvalue()


class TestAutofillSafeguards:
    """MAX_ATTACHMENTS cap, PDF text path, 400-not-502, negative-balance guard."""

    def test_max_attachments_cap(self, admin, konut_chat, tapu_upload):
        before = _balance(admin)
        ids = [tapu_upload] * 11
        r = admin.post(f"{API}/chats/{konut_chat}/autofill", json={"attachment_ids": ids})
        assert r.status_code == 400, f"{r.status_code}: {r.text[:300]}"
        detail = r.json()["detail"]
        assert "En fazla 10 dosya" in detail, detail
        assert _balance(admin) == pytest.approx(before, abs=0.01), "wallet charged on cap rejection"

    def test_exactly_10_attachments_not_rejected_by_cap(self, admin, konut_chat, txt_upload):
        """10 ids must pass the cap check (rejected later for MIME, with refund)."""
        before = _balance(admin)
        r = admin.post(f"{API}/chats/{konut_chat}/autofill",
                       json={"attachment_ids": [txt_upload] * 10})
        assert r.status_code == 400
        assert "En fazla" not in r.json()["detail"], "cap wrongly triggered at exactly 10"
        assert _balance(admin) == pytest.approx(before, abs=0.01)

    def test_pdf_autofill_via_text(self, admin, state, mongo):
        """REAL LLM call #2: PDF handled through pypdf text extraction (no renderer needed)."""
        files = {"file": ("TEST_tapu.pdf", _make_tapu_pdf(), "application/pdf")}
        up = admin.post(f"{API}/uploads", files=files)
        assert up.status_code == 200, up.text
        pdf_id = up.json()["upload_id"]
        state["uploads"].append(pdf_id)

        rc = admin.post(f"{API}/chats", json={"mode": "report", "template_id": "konut"})
        cid = rc.json()["chat"]["chat_id"]
        state["chats"].append(cid)

        before = _balance(admin)
        r = admin.post(f"{API}/chats/{cid}/autofill",
                       json={"attachment_ids": [pdf_id]}, timeout=240)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:800]}"
        d = r.json()
        print(f"\n[pdf-autofill] {json.dumps(d, ensure_ascii=False)[:700]}")
        assert d["files_analyzed"] == 1
        assert d["tokens"]["input"] > 0, "no input tokens from pypdf-extracted PDF text"
        assert d["tokens"]["output"] > 0
        assert d["cost_try"] > 0
        assert d["fields"] or d["out_of_scope"], "neither fields nor out_of_scope populated"
        after = _balance(admin)
        assert after == pytest.approx(before - d["cost_try"], abs=0.02), \
            f"wallet not decremented by cost_try: {before} -> {after}, cost={d['cost_try']}"
        assert after >= 0, "wallet went negative"

        ev = mongo.usage_events.find_one({"chat_id": cid, "mode": "autofill"},
                                         sort=[("created_at", -1)])
        assert ev is not None
        assert ev["input_tokens"] == d["tokens"]["input"]
        assert ev["output_tokens"] == d["tokens"]["output"]
        assert ev["actual_ai_cost_try"] > 0
        assert ev["file_count"] == 1

    def test_llm_failure_returns_400_not_502(self, admin, state, mongo):
        """Real provider error: an oversized image (>5MB base64) is rejected by Anthropic.
        The endpoint must answer 400 with a JSON detail (not 502/HTML) and refund the hold."""
        import random
        from PIL import Image
        random.seed(7)
        n = 2600
        img = Image.frombytes("RGB", (n, n), bytes(random.getrandbits(8) for _ in range(n * n * 3)))
        buf = io.BytesIO()
        img.save(buf, format="PNG", compress_level=0)
        blob = buf.getvalue()
        print(f"\n[oversize] png bytes={len(blob)}")

        up = admin.post(f"{API}/uploads", files={"file": ("TEST_huge.png", blob, "image/png")})
        if up.status_code != 200:
            pytest.skip(f"upload of oversized image rejected by /uploads ({up.status_code})")
        big_id = up.json()["upload_id"]
        state["uploads"].append(big_id)

        rc = admin.post(f"{API}/chats", json={"mode": "report", "template_id": "konut"})
        cid = rc.json()["chat"]["chat_id"]
        state["chats"].append(cid)

        before = _balance(admin)
        r = admin.post(f"{API}/chats/{cid}/autofill",
                       json={"attachment_ids": [big_id]}, timeout=300)
        print(f"[oversize] status={r.status_code} body={r.text[:300]}")
        if r.status_code == 200:
            pytest.skip("provider accepted the oversized image; LLM-failure path not exercised")
        assert r.status_code == 400, f"expected 400 JSON error, got {r.status_code}"
        assert r.headers.get("content-type", "").startswith("application/json"), \
            "error body is not JSON (ingress HTML page)"
        assert "Analiz başarısız" in r.json()["detail"]
        after = _balance(admin)
        assert after == pytest.approx(before, abs=0.01), f"hold not refunded: {before} -> {after}"
        # temp file must not be left behind on the failure branch (20 MB leak per attempt)
        leftovers = list((Path("/app/backend/generated_reports") / cid / "_autofill").glob("*")) \
            if (Path("/app/backend/generated_reports") / cid / "_autofill").exists() else []
        assert not leftovers, f"temp files leaked on LLM-failure branch: {leftovers}"

    def test_no_502_in_autofill_handler(self):
        src = Path("/app/backend/server.py").read_text(encoding="utf-8")
        start = src.index("async def autofill_chat_from_attachments")
        end = src.index("@api.patch(\"/chats/{chat_id}/fields\")")
        block = src[start:end]
        assert "status_code=502" not in block, "autofill still raises 502"
        assert "status_code=400, detail=f\"Analiz başarısız" in block, \
            "LLM failure branch does not return 400 JSON"

    def test_wallet_never_negative(self, admin, mongo):
        u = mongo.users.find_one({"session_token": None, "user_id": "user_grelligram_seed"}) or \
            mongo.users.find_one({"user_id": "user_grelligram_seed"})
        assert u is not None
        assert float(u["wallet_balance"]) >= 0, f"wallet negative: {u['wallet_balance']}"

    def test_negative_balance_guard_code(self):
        """Guard must deduct the delta only when the wallet can cover it."""
        src = Path("/app/backend/server.py").read_text(encoding="utf-8")
        start = src.index("async def autofill_chat_from_attachments")
        end = src.index("@api.patch(\"/chats/{chat_id}/fields\")")
        block = src[start:end]
        assert "wallet_balance\": {\"$gte\": extra}" in block, "no atomic guarded deduction for delta"
        assert "charged_try = NOMINAL_HOLD" in block, "no cap fallback when wallet cannot cover delta"


# ---------------------------------------------------------------- PATCH /fields
class TestPatchFields:
    def test_merge_fields(self, admin, konut_chat):
        r = admin.patch(f"{API}/chats/{konut_chat}/fields",
                        json={"fields": {"a": "x", "b": "y"}})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["success"] is True
        assert d["fields"]["a"] == "x" and d["fields"]["b"] == "y"

        g = admin.get(f"{API}/chats/{konut_chat}")
        assert g.status_code == 200
        persisted = g.json()["chat"]["fields"] if "chat" in g.json() else g.json()["fields"]
        assert persisted["a"] == "x" and persisted["b"] == "y"

    def test_clear_and_empty_value_removal(self, admin, konut_chat):
        admin.patch(f"{API}/chats/{konut_chat}/fields", json={"fields": {"c": "z", "d": "w"}})
        r = admin.patch(f"{API}/chats/{konut_chat}/fields",
                        json={"fields": {"d": ""}, "clear": ["c"]})
        assert r.status_code == 200, r.text
        f = r.json()["fields"]
        assert "c" not in f, "clear[] did not remove key"
        assert "d" not in f, "empty value did not remove key"
        assert f["a"] == "x", "unrelated keys must survive the merge"

    def test_patch_unknown_chat_404(self, admin):
        r = admin.patch(f"{API}/chats/chat_nope/fields", json={"fields": {"a": "1"}})
        assert r.status_code == 404

    def test_patch_other_users_chat_404(self, poor_client, konut_chat):
        r = poor_client.patch(f"{API}/chats/{konut_chat}/fields", json={"fields": {"hack": "1"}})
        assert r.status_code == 404


# ---------------------------------------------------------------- SSE regression: 1 REAL call
class TestMessageSSERegression:
    text = ""

    def test_out_of_scope_and_token_accounting(self, admin, mongo, state):
        r = admin.post(f"{API}/chats", json={"mode": "faq"})
        assert r.status_code == 200, r.text
        cid = r.json()["chat"]["chat_id"]
        state["chats"].append(cid)

        before = _balance(admin)
        resp = admin.post(f"{API}/chats/{cid}/message",
                          json={"content": "İtalyan mutfağı için makarna tarifi ver"},
                          stream=True, timeout=240)
        assert resp.status_code == 200, f"{resp.status_code}: {resp.text[:500]}"
        parts, done = [], None
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            ev = json.loads(line[6:])
            if ev.get("type") == "delta":
                parts.append(ev["content"])
            elif ev.get("type") == "error":
                pytest.fail(f"SSE error event: {ev}")
            elif ev.get("type") == "done":
                done = ev
        full = "".join(parts)
        TestMessageSSERegression.text = full
        print(f"\n[sse] len={len(full)} chars | {full[:400]}")
        assert full.strip(), "assistant produced no text"
        assert done is not None, "no 'done' event received"

        # scope guard
        low = full.lower()
        assert ("kapsam" in low or "dışında" in low or "disinda" in low), \
            f"scope guard did not trigger: {full[:300]}"

        # max_tokens=1024 cap => bounded length (1024 tok ~ <= 4500 chars for Turkish)
        assert len(full) < 6000, f"response longer than 1024-token cap suggests: {len(full)} chars"

        # wallet deducted by the flat per-message cost
        after = _balance(admin)
        assert after < before, "message did not deduct from wallet"

        # real token counting written back to usage_events
        ev = None
        for _ in range(10):
            ev = mongo.usage_events.find_one({"chat_id": cid}, sort=[("created_at", -1)])
            if ev and ev.get("input_tokens"):
                break
            time.sleep(1)
        assert ev is not None, "no usage_events row for the message"
        assert ev.get("input_tokens", 0) > 0, f"input_tokens not recorded: {ev}"
        assert ev.get("output_tokens", 0) > 0, f"output_tokens not recorded: {ev}"
        assert ev.get("actual_ai_cost_try", 0) > 0, f"actual_ai_cost_try not recorded: {ev}"
        assert ev.get("actual_ai_cost_usd", 0) > 0
        expected_usd = (ev["input_tokens"] / 1e6) * 2.0 + (ev["output_tokens"] / 1e6) * 10.0
        assert ev["actual_ai_cost_usd"] == pytest.approx(round(expected_usd, 6), abs=1e-6)
        assert ev["actual_ai_cost_try"] == pytest.approx(round(expected_usd * USD_TRY, 4), abs=1e-3)

    def test_max_tokens_cap_enforced(self, admin, mongo, state):
        """A deliberately verbose in-scope prompt must still be capped at max_tokens=1024."""
        r = admin.post(f"{API}/chats", json={"mode": "faq"})
        cid = r.json()["chat"]["chat_id"]
        state["chats"].append(cid)
        resp = admin.post(
            f"{API}/chats/{cid}/message",
            json={"content": "SPK gayrimenkul değerleme mevzuatını, emsal karşılaştırma, "
                             "gelir indirgeme ve maliyet yaklaşımlarını mümkün olan en uzun "
                             "ve en detaylı şekilde, tüm alt başlıklarıyla anlat."},
            stream=True, timeout=240)
        assert resp.status_code == 200, resp.text[:300]
        parts = []
        for line in resp.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                ev = json.loads(line[6:])
                if ev.get("type") == "delta":
                    parts.append(ev["content"])
                elif ev.get("type") == "error":
                    pytest.fail(f"SSE error: {ev}")
        full = "".join(parts)
        print(f"\n[sse-cap] len={len(full)} chars")
        ev = None
        for _ in range(10):
            ev = mongo.usage_events.find_one({"chat_id": cid}, sort=[("created_at", -1)])
            if ev and ev.get("output_tokens"):
                break
            time.sleep(1)
        assert ev and ev.get("output_tokens", 0) > 0, f"tokens missing: {ev}"
        print(f"[sse-cap] tokens in={ev['input_tokens']} out={ev['output_tokens']}")
        assert ev["output_tokens"] <= 1024, f"max_tokens=1024 not applied: {ev['output_tokens']}"

    def test_message_unknown_chat_404(self, admin):
        r = admin.post(f"{API}/chats/chat_nope/message", json={"content": "merhaba"})
        assert r.status_code == 404, r.status_code
