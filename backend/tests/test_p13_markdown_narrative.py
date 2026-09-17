"""Iteration 13: markdown-render / narrative-autofill / image-assignment tests.

Covers:
  * POST /api/chats/{id}/autofill returns new keys `missing_critical` and
    `image_assignments` (always arrays, even when Claude did not populate them).
  * PATCH /api/chats/{id}/fields accepts image-dict field values without rejection.
  * POST /api/chats/{id}/message SSE runs cleanly for a user_template chat that
    contains narrative-flagged fields (no Python exception in _build_system_prompt).
"""
import io
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"

backend_env = dotenv_values("/app/backend/.env")
MONGO_URL = os.environ.get("MONGO_URL") or backend_env.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or backend_env.get("DB_NAME")

SUPER_TOKEN = "test_super_admin_token"


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


# ------------------------- helpers ---------------------------------------
def _make_tapu_png_with_photo_slots() -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (760, 460), "white")
    d = ImageDraw.Draw(img)
    font = None
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",):
        if Path(p).exists():
            font = ImageFont.truetype(p, 20)
            break
    lines = [
        "TAPU KAYIT BELGESI",
        "Il: Ankara   Ilce: Cankaya",
        "Ada / Parsel No: 1234 / 56",
        "Acik Adres: Kizilay Mah. Ataturk Cad. No 12 D:5",
        "Brut Alan: 145 m2   Net Alan: 128 m2",
        "Oda Sayisi: 3+1  Bina Yasi: 12  Kat: 4",
        "Isitma: Dogalgaz Kombi",
        "Davaci iddiasi: Mulkiyet hakki ihlal edilmistir.",
        "Bilirkisi degerlendirmesi: Emsal analizi yapilmistir.",
    ]
    y = 15
    for ln in lines:
        d.text((15, y), ln, fill="black", font=font)
        y += 40
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _seed_user_template(mongo, state) -> str:
    tid = f"TEST_p13_ut_{uuid.uuid4().hex[:8]}"
    doc = {
        "template_id": tid,
        "name": "TEST P13 Hukuki Rapor",
        "user_id": "user_grelligram_seed",
        "shared_with": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "fields": [
            {"key": "davaci_ad", "label": "Davacı Adı", "type": "text"},
            {"key": "davaci_iddia", "label": "Davacı İddiaları",
             "type": "textarea", "hint": "Davacının hukuki iddialarını uzun paragraf olarak yaz."},
            {"key": "bilirkisi_degerlendirme", "label": "Bilirkişi Değerlendirmesi",
             "type": "textarea", "hint": "Teknik değerlendirme."},
            {"key": "cephe_foto", "label": "Cephe Fotoğrafı", "type": "image"},
        ],
        "sections": ["Giriş", "Değerlendirme"],
        "original_docx_path": None,
        "prepared_docx_path": None,
    }
    mongo.user_templates.insert_one(doc)
    state["user_templates"].append(tid)
    return tid


# ------------------------- tests -----------------------------------------

class TestPatchFieldsAcceptsImageDict:
    """PATCH /chats/{id}/fields must accept image-value dicts as legitimate values."""

    def test_image_dict_accepted_and_persisted(self, admin, mongo, state):
        # Use a builtin konut chat (image dict is generic, template-agnostic)
        r = admin.post(f"{API}/chats", json={"mode": "report", "template_id": "konut"})
        assert r.status_code == 200, r.text
        cid = r.json()["chat"]["chat_id"]
        state["chats"].append(cid)

        image_value = {
            "__image__": True,
            "storage_path": "uploads/fake/path.png",
            "upload_id": "up_faketest_p13",
            "preview_url": "/api/uploads/file/up_faketest_p13",
            "filename": "cephe.png",
            "width_mm": 90,
        }
        r = admin.patch(f"{API}/chats/{cid}/fields",
                        json={"fields": {"cephe_foto": image_value, "kisi": "Ali"}})
        assert r.status_code == 200, r.text
        f = r.json()["fields"]
        assert f.get("kisi") == "Ali", "regular string field lost"
        got = f.get("cephe_foto")
        assert isinstance(got, dict), f"image value not stored as dict: {got!r}"
        assert got.get("__image__") is True
        assert got.get("upload_id") == "up_faketest_p13"
        assert got.get("filename") == "cephe.png"
        assert got.get("width_mm") == 90

        # verify persistence via GET
        g = admin.get(f"{API}/chats/{cid}")
        assert g.status_code == 200
        j = g.json()
        persisted = j["chat"]["fields"] if "chat" in j else j["fields"]
        assert isinstance(persisted.get("cephe_foto"), dict)
        assert persisted["cephe_foto"].get("__image__") is True

    def test_image_dict_can_be_cleared(self, admin, state):
        r = admin.post(f"{API}/chats", json={"mode": "report", "template_id": "konut"})
        cid = r.json()["chat"]["chat_id"]
        state["chats"].append(cid)
        img = {"__image__": True, "storage_path": "x", "upload_id": "u",
               "preview_url": "/p", "filename": "x.png", "width_mm": 80}
        admin.patch(f"{API}/chats/{cid}/fields", json={"fields": {"slot": img}})
        # clear via clear[]
        r = admin.patch(f"{API}/chats/{cid}/fields", json={"clear": ["slot"]})
        assert r.status_code == 200
        assert "slot" not in r.json()["fields"]


class TestAutofillNewKeys:
    """POST /chats/{id}/autofill must return image_assignments + missing_critical arrays."""

    result = {}

    def test_autofill_returns_new_response_keys(self, admin, mongo, state):
        # Upload a tapu-ish PNG
        blob = _make_tapu_png_with_photo_slots()
        up = admin.post(f"{API}/uploads",
                        files={"file": ("TEST_p13_tapu.png", blob, "image/png")})
        assert up.status_code == 200, up.text
        uid = up.json()["upload_id"]
        state["uploads"].append(uid)

        # Create a user_template chat that includes an image slot + narrative textarea
        tid = _seed_user_template(mongo, state)
        rc = admin.post(f"{API}/chats", json={"mode": "report", "user_template_id": tid})
        assert rc.status_code == 200, rc.text
        cid = rc.json()["chat"]["chat_id"]
        state["chats"].append(cid)

        r = admin.post(f"{API}/chats/{cid}/autofill",
                       json={"attachment_ids": [uid]}, timeout=300)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:800]}"
        d = r.json()
        TestAutofillNewKeys.result = d
        print(f"\n[autofill-p13] keys={list(d.keys())}")
        print(f"[autofill-p13] fields={list((d.get('fields') or {}).keys())}")
        print(f"[autofill-p13] missing_critical={d.get('missing_critical')}")
        print(f"[autofill-p13] image_assignments count={len(d.get('image_assignments') or [])}")

        for k in ("fields", "duplicates", "out_of_scope", "notes", "tokens",
                  "cost_try", "wallet_balance", "files_analyzed",
                  "missing_critical", "image_assignments"):
            assert k in d, f"missing key {k}"

        # both new arrays must be arrays even when empty
        assert isinstance(d["missing_critical"], list)
        assert isinstance(d["image_assignments"], list)

        # image_assignments entries (when present) must have the fields the FE relies on
        for a in d["image_assignments"]:
            assert isinstance(a, dict)
            for kk in ("field_key", "upload_id", "filename", "preview_url", "value"):
                assert kk in a, f"image_assignments entry missing '{kk}': {a}"
            v = a["value"]
            assert isinstance(v, dict)
            assert v.get("__image__") is True
            assert v.get("upload_id") == a["upload_id"]
            assert v.get("storage_path")
            # field_key must be a real image slot on the template
            assert a["field_key"] == "cephe_foto"

        # missing_critical entries (when present) must have field+question
        for m in d["missing_critical"]:
            assert isinstance(m, dict)
            assert "field" in m and "question" in m
            assert m["question"]

    def test_autofill_response_image_value_is_patchable(self, admin, state):
        """The image_assignments[].value dict must be accepted by PATCH /fields
        (this is the exact end-to-end flow triggered by 'Onayla ve Doldur')."""
        d = TestAutofillNewKeys.result
        if not d:
            pytest.skip("autofill did not run")
        if not d.get("image_assignments"):
            pytest.skip("Claude did not produce an image_map; nothing to patch")
        # patch onto the same chat (last one in state)
        cid = state["chats"][-1]
        merged = {a["field_key"]: a["value"] for a in d["image_assignments"]}
        r = admin.patch(f"{API}/chats/{cid}/fields", json={"fields": merged})
        assert r.status_code == 200, r.text
        for fk, val in merged.items():
            assert r.json()["fields"].get(fk, {}).get("__image__") is True


class TestUserTemplateSSE:
    """Regression: SSE endpoint runs without exception for a narrative user_template chat."""

    def test_user_template_sse_smoke(self, admin, mongo, state):
        tid = _seed_user_template(mongo, state)
        r = admin.post(f"{API}/chats", json={"mode": "report", "user_template_id": tid})
        assert r.status_code == 200, r.text
        cid = r.json()["chat"]["chat_id"]
        state["chats"].append(cid)

        # Prime chat.fields with something so `collected` is non-empty (exercises narrative_hint branch)
        admin.patch(f"{API}/chats/{cid}/fields",
                    json={"fields": {"davaci_ad": "Ahmet Yılmaz"}})

        resp = admin.post(f"{API}/chats/{cid}/message",
                          json={"content": "Davacı iddialarını **kalın** yaz, *italik* örnek ver, "
                                            "madde madde listele."},
                          stream=True, timeout=240)
        assert resp.status_code == 200, resp.text[:500]
        parts, done, err = [], None, None
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            ev = json.loads(line[6:])
            if ev.get("type") == "delta":
                parts.append(ev.get("content", ""))
            elif ev.get("type") == "error":
                err = ev
            elif ev.get("type") == "done":
                done = ev
        full = "".join(parts)
        print(f"\n[sse-p13] len={len(full)} err={err} sample={full[:300]!r}")
        assert err is None, f"SSE error event received: {err}"
        assert done is not None, "no 'done' SSE event"
        assert full.strip(), "assistant produced no text (user_template prompt likely raised)"
        # Soft check: markdown was requested; expect at least one markdown token in output
        # (bold/italic/list). Not strict — Claude sometimes ignores; just log.
        has_md = any(tok in full for tok in ("**", "* ", "- ", "\n1.", "##"))
        print(f"[sse-p13] contains-markdown-marker={has_md}")
