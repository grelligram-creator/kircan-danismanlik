"""v7 feature tests: dynamic tables, image resizing (width_mm), template sharing ACL."""
import io
import os
import re

import pytest
import requests
from docx import Document
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = base_url.rstrip("/") + "/api"

OWNER_TOKEN = "test_session_seed_001"
SHARED_TOKEN = "test_session_shared_002"
SHARED_EMAIL = "shared@example.com"
TABLE_TPL = "utpl_bbbe8c680d96"   # Emsal Testi, karsilastirma_emsalleri (adres/alan/fiyat)
IMAGE_TPL = "utpl_c200aa15fd4d"   # Test Konut Şablonu, cephe_fotografi/uydu_goruntusu
import base64
PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAADwAAAAoCAIAAAAt2Q6oAAAASklEQVR4nO3OQQ3AIAAAMUDSNCEWWfOw"
    "x5ElrYLOs5/xN+t24AvpinRFuiJdka5IV6Qr0hXpinRFuiJdka5IV6Qr0hXpinRFuvICMlcBrtc6zHsA"
    "AAAASUVORK5CYII="
)


def client(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def owner():
    return client(OWNER_TOKEN)


@pytest.fixture(scope="module")
def shared():
    return client(SHARED_TOKEN)


@pytest.fixture(scope="module")
def created_chats():
    ids = []
    yield ids
    for cid, tok in ids:
        client(tok).delete(f"{BASE}/chats/{cid}")


def _new_chat(sess, user_template_id, created_chats, token):
    r = sess.post(f"{BASE}/chats", json={"user_template_id": user_template_id})
    assert r.status_code == 200, r.text
    cid = r.json()["chat"]["chat_id"]
    created_chats.append((cid, token))
    return cid


# ---------------------------------------------------------------- sanity/auth
class TestSanity:
    def test_owner_auth(self, owner):
        r = owner.get(f"{BASE}/auth/me")
        assert r.status_code == 200, r.text
        assert r.json()["user_id"] == "test-user-seed-001"

    def test_shared_user_auth(self, shared):
        r = shared.get(f"{BASE}/auth/me")
        assert r.status_code == 200, r.text
        assert r.json()["email"] == SHARED_EMAIL


# ---------------------------------------------------------------- table field
class TestTableField:
    def test_template_has_table_field(self, owner):
        r = owner.get(f"{BASE}/user_templates/{TABLE_TPL}")
        assert r.status_code == 200, r.text
        f = next(x for x in r.json()["fields"] if x["key"] == "karsilastirma_emsalleri")
        assert f["type"] == "table"
        assert [c["key"] for c in f["columns"]] == ["adres", "alan", "fiyat"]

    def test_prepared_docx_has_jinja_loop_markers(self):
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        mongo = AsyncIOMotorClient(os.environ["MONGO_URL"])

        async def _get():
            return await mongo[os.environ["DB_NAME"]].user_templates.find_one({"template_id": TABLE_TPL})
        tpl = asyncio.get_event_loop().run_until_complete(_get())
        doc = Document(tpl["prepared_docx_path"])
        text = "\n".join(c.text for t in doc.tables for row in t.rows for c in row.cells)
        assert "{%tr for" in text, text
        assert "{%tr endfor %}" in text or "endfor" in text
        assert "{{r.adres}}" in text.replace("{{ r.adres }}", "{{r.adres}}")

    def test_patch_table_persists(self, owner, created_chats):
        cid = _new_chat(owner, TABLE_TPL, created_chats, OWNER_TOKEN)
        rows = [
            {"adres": "TEST_Kadikoy", "alan": "120", "fiyat": "50000"},
            {"adres": "TEST_Atasehir", "alan": "100", "fiyat": "48000"},
            {"adres": "TEST_Uskudar", "alan": "110", "fiyat": "52000"},
            {"adres": "TEST_Maltepe", "alan": "95", "fiyat": "41000"},
        ]
        r = owner.patch(f"{BASE}/chats/{cid}/table/karsilastirma_emsalleri", json={"rows": rows})
        assert r.status_code == 200, r.text
        assert r.json()["success"] is True
        assert r.json()["rows"] == rows
        # verify persistence
        g = owner.get(f"{BASE}/chats/{cid}")
        assert g.status_code == 200
        assert g.json()["chat"]["fields"]["karsilastirma_emsalleri"] == rows

    def test_patch_table_unknown_columns_stripped(self, owner, created_chats):
        cid = _new_chat(owner, TABLE_TPL, created_chats, OWNER_TOKEN)
        r = owner.patch(f"{BASE}/chats/{cid}/table/karsilastirma_emsalleri",
                        json={"rows": [{"adres": "A", "bogus": "x"}]})
        assert r.status_code == 200, r.text
        assert r.json()["rows"] == [{"adres": "A"}]

    def test_patch_table_invalid_field_key_404(self, owner, created_chats):
        cid = _new_chat(owner, TABLE_TPL, created_chats, OWNER_TOKEN)
        r = owner.patch(f"{BASE}/chats/{cid}/table/does_not_exist", json={"rows": []})
        assert r.status_code == 404, r.text

    def test_patch_table_rows_not_list_400(self, owner, created_chats):
        cid = _new_chat(owner, TABLE_TPL, created_chats, OWNER_TOKEN)
        r = owner.patch(f"{BASE}/chats/{cid}/table/karsilastirma_emsalleri", json={"rows": "nope"})
        assert r.status_code == 400, r.text

    def test_download_docx_row_count_matches(self, owner, created_chats):
        cid = _new_chat(owner, TABLE_TPL, created_chats, OWNER_TOKEN)
        rows = [{"adres": f"TEST_Adres{i}", "alan": str(100 + i), "fiyat": str(40000 + i)} for i in range(5)]
        assert owner.patch(f"{BASE}/chats/{cid}/table/karsilastirma_emsalleri",
                           json={"rows": rows}).status_code == 200
        r = owner.get(f"{BASE}/chats/{cid}/download/docx")
        assert r.status_code == 200, r.text[:400]
        doc = Document(io.BytesIO(r.content))
        target = None
        for t in doc.tables:
            cells = "\n".join(c.text for row in t.rows for c in row.cells)
            if "TEST_Adres0" in cells:
                target = t
                break
        assert target is not None, "rendered docx has no table containing the provided rows"
        body = [row for row in target.rows if any(c.text.strip() for c in row.cells)]
        texts = ["|".join(c.text.strip() for c in row.cells) for row in body]
        # header preserved
        assert any(("Adres" in t or "adres" in t) and "TEST_" not in t for t in texts), texts
        data_rows = [t for t in texts if "TEST_Adres" in t]
        assert len(data_rows) == 5, texts
        # no leftover jinja markers
        allcells = "\n".join(c.text for t in doc.tables for row in t.rows for c in row.cells)
        assert "{%tr" not in allcells and "{{" not in allcells, allcells

    def test_preview_expands_table_rows(self, owner, created_chats):
        cid = _new_chat(owner, TABLE_TPL, created_chats, OWNER_TOKEN)
        rows = [{"adres": "TEST_PV1", "alan": "1", "fiyat": "2"}, {"adres": "TEST_PV2", "alan": "3", "fiyat": "4"}]
        owner.patch(f"{BASE}/chats/{cid}/table/karsilastirma_emsalleri", json={"rows": rows})
        r = owner.get(f"{BASE}/user_templates/{TABLE_TPL}/preview", params={"chat_id": cid})
        assert r.status_code == 200, r.text
        html = r.json()["html"]
        assert "TEST_PV1" in html and "TEST_PV2" in html
        assert "{%tr" not in html


# ---------------------------------------------------------------- image resize
class TestImageResize:
    @pytest.fixture(scope="class")
    def img_chat(self, owner, created_chats):
        cid = _new_chat(owner, IMAGE_TPL, created_chats, OWNER_TOKEN)
        r = owner.post(f"{BASE}/chats/{cid}/image",
                       files={"file": ("TEST_pic.png", PNG_1x1, "image/png")},
                       data={"field_key": "cephe_fotografi"})
        assert r.status_code == 200, r.text
        assert r.json()["width_mm"] == 80
        return cid

    def test_patch_width(self, owner, img_chat):
        r = owner.patch(f"{BASE}/chats/{img_chat}/image/cephe_fotografi", json={"width_mm": 120})
        assert r.status_code == 200, r.text
        assert r.json()["width_mm"] == 120.0
        g = owner.get(f"{BASE}/chats/{img_chat}")
        assert g.json()["chat"]["fields"]["cephe_fotografi"]["width_mm"] == 120.0

    def test_preview_width_px(self, owner, img_chat):
        owner.patch(f"{BASE}/chats/{img_chat}/image/cephe_fotografi", json={"width_mm": 120})
        r = owner.get(f"{BASE}/user_templates/{IMAGE_TPL}/preview", params={"chat_id": img_chat})
        assert r.status_code == 200, r.text
        html = r.json()["html"]
        widths = re.findall(r"width:\s*(\d+)px", html)
        assert "453" in widths, widths

    def test_clamp_high_and_low(self, owner, img_chat):
        assert owner.patch(f"{BASE}/chats/{img_chat}/image/cephe_fotografi",
                           json={"width_mm": 500}).json()["width_mm"] == 170.0
        assert owner.patch(f"{BASE}/chats/{img_chat}/image/cephe_fotografi",
                           json={"width_mm": 1}).json()["width_mm"] == 20.0

    def test_invalid_width_400(self, owner, img_chat):
        r = owner.patch(f"{BASE}/chats/{img_chat}/image/cephe_fotografi", json={"width_mm": "abc"})
        assert r.status_code == 400, r.text

    def test_unknown_image_field_404(self, owner, img_chat):
        r = owner.patch(f"{BASE}/chats/{img_chat}/image/uydu_goruntusu", json={"width_mm": 100})
        assert r.status_code == 404, r.text

    def test_download_after_resize(self, owner, img_chat):
        owner.patch(f"{BASE}/chats/{img_chat}/image/cephe_fotografi", json={"width_mm": 140})
        r = owner.get(f"{BASE}/chats/{img_chat}/download/docx")
        assert r.status_code == 200, r.text[:300]
        import zipfile
        z = zipfile.ZipFile(io.BytesIO(r.content))
        assert any(n.startswith("word/media/") for n in z.namelist()), z.namelist()


# ---------------------------------------------------------------- sharing ACL
class TestSharing:
    @pytest.fixture(scope="class", autouse=True)
    def unshare_after(self, owner):
        yield
        owner.post(f"{BASE}/user_templates/{TABLE_TPL}/share", json={"remove": [SHARED_EMAIL]})

    def test_before_share_not_visible(self, shared):
        r = shared.get(f"{BASE}/user_templates/{TABLE_TPL}")
        assert r.status_code == 404, r.text
        lst = shared.get(f"{BASE}/user_templates").json()["templates"]
        assert TABLE_TPL not in [t["template_id"] for t in lst]

    def test_before_share_cannot_create_chat(self, shared):
        r = shared.post(f"{BASE}/chats", json={"user_template_id": TABLE_TPL})
        assert r.status_code in (400, 403, 404), f"{r.status_code} {r.text}"

    def test_owner_shares(self, owner):
        r = owner.post(f"{BASE}/user_templates/{TABLE_TPL}/share", json={"add": [SHARED_EMAIL.upper()]})
        assert r.status_code == 200, r.text
        assert SHARED_EMAIL in r.json()["shared_with"]

    def test_recipient_sees_shared_template(self, shared):
        lst = shared.get(f"{BASE}/user_templates").json()["templates"]
        item = next((t for t in lst if t["template_id"] == TABLE_TPL), None)
        assert item is not None, [t["template_id"] for t in lst]
        assert item["is_shared_with_me"] is True
        g = shared.get(f"{BASE}/user_templates/{TABLE_TPL}")
        assert g.status_code == 200
        assert g.json()["is_shared_with_me"] is True
        # also exposed under /api/templates custom list
        cts = shared.get(f"{BASE}/templates").json().get("custom_templates", [])
        assert TABLE_TPL in [t["template_id"] for t in cts]

    def test_recipient_preview_ok(self, shared):
        r = shared.get(f"{BASE}/user_templates/{TABLE_TPL}/preview")
        assert r.status_code == 200, r.text
        assert "<" in r.json()["html"]

    def test_recipient_chat_and_download(self, shared, created_chats):
        cid = _new_chat(shared, TABLE_TPL, created_chats, SHARED_TOKEN)
        rows = [{"adres": "TEST_Shared1", "alan": "10", "fiyat": "20"}]
        p = shared.patch(f"{BASE}/chats/{cid}/table/karsilastirma_emsalleri", json={"rows": rows})
        assert p.status_code == 200, p.text
        d = shared.get(f"{BASE}/chats/{cid}/download/docx")
        assert d.status_code == 200, d.text[:300]
        doc = Document(io.BytesIO(d.content))
        cells = "\n".join(c.text for t in doc.tables for row in t.rows for c in row.cells)
        assert "TEST_Shared1" in cells

    def test_recipient_cannot_patch_template(self, shared):
        r = shared.patch(f"{BASE}/user_templates/{TABLE_TPL}", json={"name": "TEST_hijack"})
        assert r.status_code == 403, f"{r.status_code} {r.text}"

    def test_recipient_cannot_delete_template(self, shared):
        r = shared.delete(f"{BASE}/user_templates/{TABLE_TPL}")
        assert r.status_code == 403, f"{r.status_code} {r.text}"

    def test_recipient_cannot_reshare(self, shared):
        r = shared.post(f"{BASE}/user_templates/{TABLE_TPL}/share", json={"add": ["x@y.com"]})
        assert r.status_code == 403, f"{r.status_code} {r.text}"

    def test_owner_cannot_share_with_self(self, owner):
        me = owner.get(f"{BASE}/auth/me").json()["email"]
        r = owner.post(f"{BASE}/user_templates/{TABLE_TPL}/share", json={"add": [me]})
        assert r.status_code == 200
        assert me.lower() not in r.json()["shared_with"]

    def test_non_shared_template_still_hidden(self, shared):
        r = shared.get(f"{BASE}/user_templates/{IMAGE_TPL}")
        assert r.status_code == 404, r.text
        c = shared.post(f"{BASE}/chats", json={"user_template_id": IMAGE_TPL})
        assert c.status_code in (400, 403, 404), f"{c.status_code} {c.text}"

    def test_unshare_revokes(self, owner, shared):
        r = owner.post(f"{BASE}/user_templates/{TABLE_TPL}/share", json={"remove": [SHARED_EMAIL]})
        assert r.status_code == 200
        assert SHARED_EMAIL not in r.json()["shared_with"]
        assert shared.get(f"{BASE}/user_templates/{TABLE_TPL}").status_code == 404

    def test_share_unknown_template_404(self, owner):
        r = owner.post(f"{BASE}/user_templates/utpl_nonexistent/share", json={"add": ["a@b.com"]})
        assert r.status_code == 404, r.text
