"""Iteration 14: expert_block + narrative_drafts + consistency_warnings tests.

Covers:
  * `kircan_knowledge.expert_block()` import & content invariants (fast, no network).
  * POST /api/chats/{id}/autofill — new response contract fields present
    (narrative_drafts, consistency_warnings) and when a Turkish legal-text PDF is
    supplied, narrative_drafts is non-empty with substantive drafts and the
    merged `fields` dict contains the draft paragraph text.
  * Insufficient balance → HTTP 402 and nominal hold is refunded.
  * SSE /api/chats/{id}/message for a mixed narrative + short-field user_template
    chat produces delta+done events with non-empty assistant text.
"""
import io
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

# --- env ---
frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"

backend_env = dotenv_values("/app/backend/.env")
MONGO_URL = os.environ.get("MONGO_URL") or backend_env.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or backend_env.get("DB_NAME")

SUPER_TOKEN = "test_super_admin_token"
SUPER_UID = "user_grelligram_seed"


# --- fixtures ---
@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    s.cookies.set("session_token", SUPER_TOKEN)
    return s


@pytest.fixture(scope="module")
def state():
    return {"chats": [], "uploads": [], "user_templates": []}


@pytest.fixture(scope="module", autouse=True)
def cleanup(state, mongo, admin):
    # Ensure wallet is topped up for module
    mongo.users.update_one({"user_id": SUPER_UID}, {"$set": {"wallet_balance": 500.0}})
    yield
    for cid in state["chats"]:
        try:
            admin.delete(f"{API}/chats/{cid}")
        except Exception:
            pass
        mongo.chats.delete_many({"chat_id": cid})
        mongo.messages.delete_many({"chat_id": cid})
        mongo.usage_events.delete_many({"chat_id": cid})
    for uid in state["uploads"]:
        mongo.uploads.delete_many({"upload_id": uid})
    for tid in state["user_templates"]:
        mongo.user_templates.delete_many({"template_id": tid})
    # Restore wallet
    mongo.users.update_one({"user_id": SUPER_UID}, {"$set": {"wallet_balance": 500.0}})


# --- helpers ---
def _make_legal_pdf() -> bytes:
    """Compact Turkish legal narrative rendered on a PNG image.

    We use a PNG (not a PDF) because Claude Vision processes images noticeably
    faster than multi-page PDFs — important for staying under the ingress
    ~100s timeout. Content still contains a cross-document inconsistency
    (cephe 25,30 m vs beyan 26,00 m) so consistency_warnings can trigger.
    Returns raw PNG bytes; the upload MIME in the caller stays image/png.
    """
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (1100, 1400), "white")
    d = ImageDraw.Draw(img)
    font = None
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",):
        if Path(p).exists():
            font = ImageFont.truetype(p, 16)
            break
    lines = [
        "DAVA DOSYASI OZETI - Ankara 7. ASHM Esas 2024/112",
        "",
        "DAVACI: Ahmet Yilmaz (TC 11111111111)",
        "DAVALI: Ankara Buyuksehir Belediyesi Baskanligi",
        "KONU: Kamulastirma bedelinin artirilmasi talebi",
        "",
        "IDDIA (Davaci dilekcesi, 10.02.2024):",
        "Muvekkile ait Cankaya Birlik Mah. 32456 ada 7 parsel 1247 m2 arsa",
        "davali idare 2021/345 encumen karari ile kamulastirilmistir.",
        "Takdir edilen 1.250.000,00 TL bedel gercek rayici yansitmamaktadir.",
        "Emsal m2 birim fiyati 3.500,00 TL'nin altinda degildir.",
        "EK-2 emsal sozlesmeleri + EK-3 gazete ilanlari mesnet gosterilmistir.",
        "Eksik bedelin yasal faiziyle tahsili talep edilmistir.",
        "",
        "SAVUNMA (Davali cevabi, 15.03.2024):",
        "Kamulastirma 2942 s.K m.11 uyarinca mevzuata uygundur.",
        "Kiymet Takdir Komisyonu inceleme tarihi rayicini esas almistir.",
        "Davacinin emsalleri konu tasinmazla imar/cephe/lokasyon bakimindan",
        "mukayese kabil degildir. EK-1 komisyon karari, EK-2 emsal dokumleri,",
        "EK-3 imar durum belgesi ibraz edilmistir. Davanin reddi istenmistir.",
        "",
        "KESIF TESPIT (12.04.2024, bilirkisi heyeti):",
        "Parsel 1247 m2 yuzolculu, cephe 25,30 m, kuzey-guney uzanimli.",
        "Bati cephesi 15 m imar yoluna, guney cephesi 12 m tali yola cepheli.",
        "Uzerinde ruhsatsiz depo (muhdesat niteligi yoktur).",
        "Imar: Ankara BBB 10.04.2024 tarih E-2345 belge, E=1.20",
        "Ticaret+Konut, bitisik nizam, min parsel derinligi 20 m.",
        "Tapu takyidat: haciz/ipotek yoktur.",
        "",
        "TUTARSIZLIK NOTU:",
        "Kesif sirasinda davaci taraf Ahmet Y. Yilmaz, tasinmaz cephesinin",
        "fiilen 26,00 m oldugunu beyan etmistir (kesif olcumu 25,30 m).",
    ]
    y = 20
    for ln in lines:
        d.text((25, y), ln, fill="black", font=font)
        y += 24
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _seed_narrative_template(mongo, state) -> str:
    tid = f"TEST_p14_ut_{uuid.uuid4().hex[:8]}"
    doc = {
        "template_id": tid,
        "name": "TEST P14 Bilirkisi Raporu",
        "user_id": SUPER_UID,
        "shared_with": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "fields": [
            {"key": "dava_esas_no", "label": "Dava Esas No", "type": "text"},
            {"key": "davaci_ad", "label": "Davacı Adı", "type": "text"},
            {"key": "parsel", "label": "Ada/Parsel", "type": "text"},
            {"key": "davaci_iddialar", "label": "Davacı İddiaları",
             "type": "textarea", "hint": "Davacının hukuki iddialarını uzun paragraf olarak yaz."},
            {"key": "davali_savunma", "label": "Davalı Savunması",
             "type": "textarea", "hint": "Savunmanın özü, itirazlar."},
            {"key": "inceleme_tespit", "label": "İnceleme ve Tespitler",
             "type": "textarea", "hint": "Keşif tespitleri."},
        ],
        "sections": ["Giris", "Degerlendirme", "Sonuc"],
        "original_docx_path": None,
        "prepared_docx_path": None,
    }
    mongo.user_templates.insert_one(doc)
    state["user_templates"].append(tid)
    return tid


# --- tests ---

class TestExpertBlock:
    """Fast import+content test for the embedded knowledge module."""

    def test_import_and_sections(self):
        from kircan_knowledge import expert_block
        s = expert_block()
        assert isinstance(s, str) and s.strip()
        assert len(s) > 5000, f"expert_block seems too short: {len(s)}"
        for marker in ("UZMAN KİMLİĞİ", "PARAGRAF STİLİ ÖRNEKLERİ", "TUTARLILIK KURALLARI"):
            assert marker in s, f"missing section: {marker}"


class TestAutofillNarrativeContract:
    """Full response contract + narrative_drafts quality on real PDF."""

    result = {}

    def test_narrative_drafts_and_consistency(self, admin, mongo, state):
        # Upload the legal PDF
        pdf = _make_legal_pdf()
        up = admin.post(f"{API}/uploads",
                        files={"file": ("TEST_p14_dava.png", pdf, "image/png")})
        assert up.status_code == 200, up.text
        uid = up.json()["upload_id"]
        state["uploads"].append(uid)

        tid = _seed_narrative_template(mongo, state)
        rc = admin.post(f"{API}/chats", json={"mode": "report", "user_template_id": tid})
        assert rc.status_code == 200, rc.text
        cid = rc.json()["chat"]["chat_id"]
        state["chats"].append(cid)

        # The Claude Vision call is slow (60-100s) and the preview ingress has a
        # ~75-100s timeout — occasional 502s are infra-flakiness, not a product bug.
        # Retry up to 2 times before failing the assertion.
        last = None
        for attempt in range(3):
            r = admin.post(f"{API}/chats/{cid}/autofill",
                           json={"attachment_ids": [uid]}, timeout=420)
            last = r
            if r.status_code == 200:
                break
            print(f"[p14] attempt {attempt + 1}: status={r.status_code}, retrying...")
            time.sleep(2)
        r = last
        assert r.status_code == 200, f"{r.status_code}: {r.text[:600]}"
        d = r.json()
        TestAutofillNarrativeContract.result = d

        print(f"\n[p14] response keys = {sorted(d.keys())}")
        print(f"[p14] fields keys    = {list((d.get('fields') or {}).keys())}")
        print(f"[p14] narrative_drafts count = {len(d.get('narrative_drafts') or [])}")
        print(f"[p14] consistency_warnings   = {d.get('consistency_warnings')}")
        print(f"[p14] missing_critical       = {d.get('missing_critical')}")
        print(f"[p14] cost_try={d.get('cost_try')} wallet={d.get('wallet_balance')} files={d.get('files_analyzed')}")

        # Full contract keys always present
        required = ["fields", "narrative_drafts", "duplicates", "out_of_scope",
                    "missing_critical", "consistency_warnings", "image_assignments",
                    "notes", "tokens", "cost_try", "wallet_balance", "files_analyzed"]
        for k in required:
            assert k in d, f"missing key: {k}"

        # Types
        assert isinstance(d["narrative_drafts"], list)
        assert isinstance(d["consistency_warnings"], list)
        assert isinstance(d["fields"], dict)
        assert isinstance(d["tokens"], dict)
        assert "input" in d["tokens"] and "output" in d["tokens"]

        # Narrative quality: expect AT LEAST 2 of 5 narrative keys populated,
        # each with 3+ sentences (merged into fields)
        narr_keys = {"davaci_iddialar", "davali_savunma", "inceleme_tespit"}
        drafts_by_field = {
            nd["field"]: nd for nd in d["narrative_drafts"]
            if isinstance(nd, dict) and nd.get("field") in narr_keys
        }
        print(f"[p14] drafts fields = {list(drafts_by_field.keys())}")

        assert len(drafts_by_field) >= 2, (
            f"Expected >=2 narrative drafts among {narr_keys}, got "
            f"{list(drafts_by_field.keys())}"
        )
        for fkey, nd in drafts_by_field.items():
            draft = (nd.get("draft") or "").strip()
            # count sentences (ends with . ! ? or Turkish full stop)
            sent_count = sum(draft.count(x) for x in (".", "!", "?"))
            print(f"[p14]   {fkey}: {sent_count} sentences, {len(draft)} chars")
            assert sent_count >= 3, f"draft '{fkey}' too short ({sent_count} sentences): {draft[:200]}"
            assert isinstance(nd.get("sources", []), list)
            assert isinstance(nd.get("followup_questions", []), list)

            # Merged into `fields` so single PATCH flow fills them in
            assert fkey in d["fields"], f"narrative draft {fkey} not merged into fields"
            assert d["fields"][fkey].strip().startswith(draft[:30].strip()[:20]) or draft[:50] in d["fields"][fkey]

    def test_insufficient_balance_returns_402(self, admin, mongo, state):
        # Need a fresh chat + upload — reuse existing upload if any
        if not state["uploads"]:
            pytest.skip("no upload available")
        uid = state["uploads"][0]
        tid = state["user_templates"][0] if state["user_templates"] else _seed_narrative_template(mongo, state)

        # Drain wallet
        mongo.users.update_one({"user_id": SUPER_UID}, {"$set": {"wallet_balance": 0.01}})
        try:
            rc = admin.post(f"{API}/chats", json={"mode": "report", "user_template_id": tid})
            assert rc.status_code == 200
            cid = rc.json()["chat"]["chat_id"]
            state["chats"].append(cid)

            r = admin.post(f"{API}/chats/{cid}/autofill",
                           json={"attachment_ids": [uid]}, timeout=60)
            assert r.status_code == 402, f"expected 402, got {r.status_code}: {r.text[:400]}"
            # Hold must be refunded — wallet should remain near 0.01
            u = mongo.users.find_one({"user_id": SUPER_UID}, {"wallet_balance": 1})
            print(f"[p14] wallet after 402 = {u.get('wallet_balance')}")
            assert float(u.get("wallet_balance", 0)) >= 0.01 - 0.001
        finally:
            # Restore wallet for SSE test
            mongo.users.update_one({"user_id": SUPER_UID}, {"$set": {"wallet_balance": 500.0}})


class TestSSENarrativeChat:
    """SSE message for mixed-field user_template chat emits delta+done+text."""

    def test_sse_delta_and_done(self, admin, mongo, state):
        tid = state["user_templates"][0] if state["user_templates"] else _seed_narrative_template(mongo, state)
        rc = admin.post(f"{API}/chats", json={"mode": "report", "user_template_id": tid})
        assert rc.status_code == 200
        cid = rc.json()["chat"]["chat_id"]
        state["chats"].append(cid)

        # Prime some fields so the "collected" branch runs and narrative_hint is injected
        admin.patch(f"{API}/chats/{cid}/fields", json={"fields": {
            "dava_esas_no": "2024/112 E.",
            "davaci_ad": "Ahmet Yilmaz",
            "parsel": "32456 ada 7 parsel",
        }})

        # Open SSE stream
        with admin.post(f"{API}/chats/{cid}/message",
                        json={"content": "Davacı iddialarının taslağını hazırla.",
                              "stream": True},
                        stream=True, timeout=180) as resp:
            assert resp.status_code == 200, f"{resp.status_code}: {resp.text[:300]}"
            saw_delta = False
            saw_done = False
            saw_error = None
            text_buf = []
            done_payload = None
            t0 = time.time()
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw or not raw.startswith("data:"):
                    continue
                payload = raw[5:].strip()
                if not payload:
                    continue
                try:
                    obj = json.loads(payload)
                except Exception:
                    continue
                t = obj.get("type")
                if t == "delta":
                    saw_delta = True
                    text_buf.append(obj.get("content") or "")
                elif t == "done":
                    saw_done = True
                    done_payload = obj
                elif t == "error":
                    saw_error = obj
                if time.time() - t0 > 170:
                    break

            full = "".join(text_buf)
            if not full and done_payload:
                full = (done_payload.get("assistant_message") or {}).get("content") or ""
            print(f"\n[p14-sse] delta={saw_delta} done={saw_done} err={saw_error} text_len={len(full)}")
            print(f"[p14-sse] text preview: {full[:300]}")
            assert saw_error is None, f"SSE error: {saw_error}"
            assert saw_done, "no done event observed"
            assert full.strip(), "assistant text was empty (delta+done payload)"
