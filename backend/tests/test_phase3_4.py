"""Phase 3 + Phase 4 backend tests.

Covers:
  - POST /api/kb/faq            (inline FAQ creation, RBAC, validation)  [knowledge_base.py]
  - GET  /api/kb/list           (FAQ appears with kind='faq')
  - POST /api/chats/{id}/grammar-check  (validation, balance, 1 real Claude call, usage_events)
  - GET  /api/chats/{id}/download/udf   (ZIP + content.xml structure, offsets, bold, values)

NOTE: real LLM calls limited to 1 for the whole module (grammar check).
"""
import io
import os
import re
import zipfile
from datetime import datetime, timedelta, timezone

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

SUPER_TOKEN = "test_super_admin_token"
USER_TOKEN = "test_session_seed_001"
ADMIN_TOKEN = "TEST_p34_admin_token"
ADMIN_USER_ID = "TEST_p34_admin_001"
POOR_TOKEN = "TEST_p34_poor_token"
POOR_USER_ID = "TEST_p34_poor_001"


# ---------------------------------------------------------------- fixtures
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
def user_client():
    s = requests.Session()
    s.cookies.set("session_token", USER_TOKEN)
    return s


@pytest.fixture(scope="module")
def state():
    return {"chats": [], "faqs": [], "companies": []}


@pytest.fixture(scope="module", autouse=True)
def cleanup(state, mongo, admin):
    yield
    for cid in state["chats"]:
        mongo.chats.delete_many({"chat_id": cid})
        mongo.messages.delete_many({"chat_id": cid})
        mongo.usage_events.delete_many({"chat_id": cid})
    for did in state["faqs"]:
        mongo.kb_docs.delete_many({"doc_id": did})
    mongo.kb_docs.delete_many({"question": {"$regex": "^TEST_"}})
    for co in state["companies"]:
        mongo.companies.delete_many({"company_id": co})
    mongo.users.delete_one({"user_id": ADMIN_USER_ID})
    mongo.user_sessions.delete_one({"session_token": ADMIN_TOKEN})
    mongo.users.delete_one({"user_id": POOR_USER_ID})
    mongo.user_sessions.delete_one({"session_token": POOR_TOKEN})
    mongo.chats.delete_many({"user_id": POOR_USER_ID})


def _seed_session(mongo, user_id, token, **fields):
    doc = {
        "user_id": user_id, "blocked": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    doc.update(fields)
    mongo.users.update_one({"user_id": user_id}, {"$set": doc}, upsert=True)
    mongo.user_sessions.update_one(
        {"session_token": token},
        {"$set": {"session_token": token, "user_id": user_id,
                  "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
                  "created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    s = requests.Session()
    s.cookies.set("session_token", token)
    return s


@pytest.fixture(scope="module")
def company_id(admin, state):
    r = admin.post(f"{API}/admin/companies", json={"name": "TEST_P34 Şirket A.Ş."})
    assert r.status_code == 200, r.text
    cid = r.json()["company"]["company_id"]
    state["companies"].append(cid)
    return cid


@pytest.fixture(scope="module")
def company_admin(mongo, company_id):
    """A role='admin' user attached to a company (for company-scoped FAQ)."""
    return _seed_session(
        mongo, ADMIN_USER_ID, ADMIN_TOKEN,
        email="TEST_p34_admin@example.test", name="TEST P34 Admin",
        role="admin", company_id=company_id, wallet_balance=100.0,
    )


@pytest.fixture(scope="module")
def poor_client(mongo):
    return _seed_session(
        mongo, POOR_USER_ID, POOR_TOKEN,
        email="TEST_p34_poor@example.test", name="TEST P34 Poor",
        role="user", company_id=None, wallet_balance=1.0,
    )


# ================================================================ POST /api/kb/faq
class TestFAQCreate:
    def test_super_admin_can_add_global_faq(self, admin, mongo, state):
        payload = {"question": "TEST_Kapitalizasyon oranı nedir?",
                   "answer": "TEST_Net işletme gelirinin piyasa değerine oranıdır.",
                   "scope": "global"}
        r = admin.post(f"{API}/kb/faq", json=payload)
        assert r.status_code == 200, r.text
        item = r.json()["item"]
        state["faqs"].append(item["doc_id"])
        assert item["doc_id"].startswith("faq_")
        assert item["kind"] == "faq"
        assert item["question"] == payload["question"]
        assert item["answer"] == payload["answer"]
        assert item["scope"] == "global"
        assert item["company_id"] is None
        assert "_id" not in item and "text_content" not in item
        # Mongo persistence
        rec = mongo.kb_docs.find_one({"doc_id": item["doc_id"]})
        assert rec is not None
        assert rec["kind"] == "faq"
        assert rec["scope"] == "global"
        assert rec["text_content"].startswith("SORU: ")
        assert payload["answer"] in rec["text_content"]

    def test_admin_can_add_company_faq(self, company_admin, company_id, mongo, state):
        r = company_admin.post(f"{API}/kb/faq", json={
            "question": "TEST_Şirket içi emsal kaynağı?",
            "answer": "TEST_Kurum içi emsal veritabanı kullanılır.",
            "scope": "company"})
        assert r.status_code == 200, r.text
        item = r.json()["item"]
        state["faqs"].append(item["doc_id"])
        assert item["scope"] == "company"
        assert item["company_id"] == company_id
        assert item["kind"] == "faq"
        rec = mongo.kb_docs.find_one({"doc_id": item["doc_id"]})
        assert rec["company_id"] == company_id

    def test_regular_user_forbidden(self, user_client):
        r = user_client.post(f"{API}/kb/faq", json={
            "question": "TEST_yetkisiz", "answer": "TEST_yetkisiz", "scope": "global"})
        assert r.status_code == 403, r.text

    @pytest.mark.parametrize("payload", [
        {"answer": "TEST_sadece cevap", "scope": "global"},
        {"question": "TEST_sadece soru", "scope": "global"},
        {"question": "   ", "answer": "   ", "scope": "global"},
    ])
    def test_validation(self, admin, payload):
        r = admin.post(f"{API}/kb/faq", json=payload)
        assert r.status_code == 400, r.text

    def test_invalid_scope(self, admin):
        r = admin.post(f"{API}/kb/faq", json={
            "question": "TEST_q", "answer": "TEST_a", "scope": "planet"})
        assert r.status_code == 400, r.text

    def test_global_scope_requires_super(self, company_admin):
        r = company_admin.post(f"{API}/kb/faq", json={
            "question": "TEST_global deneme", "answer": "TEST_a", "scope": "global"})
        assert r.status_code == 403, r.text

    def test_unauthenticated(self):
        r = requests.post(f"{API}/kb/faq", json={"question": "TEST_q", "answer": "TEST_a"})
        assert r.status_code in (401, 403), r.text


class TestFAQList:
    def test_faq_appears_in_list(self, admin, state):
        r = admin.post(f"{API}/kb/faq", json={
            "question": "TEST_Listede görünür mü?", "answer": "TEST_Evet.", "scope": "global"})
        assert r.status_code == 200, r.text
        doc_id = r.json()["item"]["doc_id"]
        state["faqs"].append(doc_id)
        lst = admin.get(f"{API}/kb/list")
        assert lst.status_code == 200, lst.text
        docs = lst.json()["documents"]
        match = [d for d in docs if d["doc_id"] == doc_id]
        assert match, "created FAQ missing from /kb/list"
        d = match[0]
        assert d["kind"] == "faq"
        assert d["question"] == "TEST_Listede görünür mü?"
        assert "_id" not in d

    def test_regular_user_sees_global_faq(self, user_client, state):
        lst = user_client.get(f"{API}/kb/list")
        assert lst.status_code == 200, lst.text
        ids = {d["doc_id"] for d in lst.json()["documents"]}
        assert any(f in ids for f in state["faqs"]), "global FAQ not visible to regular user"


# ================================================== POST /api/chats/{id}/grammar-check
@pytest.fixture(scope="module")
def grammar_chat(admin, state):
    r = admin.post(f"{API}/chats", json={"mode": "report", "template_id": "konut"})
    assert r.status_code == 200, r.text
    cid = r.json()["chat"]["chat_id"]
    state["chats"].append(cid)
    return cid


class TestGrammarCheck:
    def test_chat_not_found(self, admin):
        r = admin.post(f"{API}/chats/chat_nope_xyz/grammar-check")
        assert r.status_code == 404, r.text

    def test_no_text_returns_400(self, admin, grammar_chat):
        r = admin.post(f"{API}/chats/{grammar_chat}/grammar-check")
        assert r.status_code == 400, r.text
        assert "Kontrol edilecek metin bulunamadı" in r.json()["detail"]

    def test_insufficient_balance(self, poor_client, state, mongo):
        c = poor_client.post(f"{API}/chats", json={"mode": "report", "template_id": "konut"})
        assert c.status_code == 200, c.text
        cid = c.json()["chat"]["chat_id"]
        state["chats"].append(cid)
        p = poor_client.patch(f"{API}/chats/{cid}/fields",
                              json={"fields": {"adres": "ıstanbul kadıköy"}})
        assert p.status_code == 200, p.text
        r = poor_client.post(f"{API}/chats/{cid}/grammar-check")
        assert r.status_code == 402, r.text
        detail = r.json()["detail"]
        assert detail["error"] == "insufficient_balance"
        assert detail["required"] == 3.0
        # wallet untouched
        u = mongo.users.find_one({"user_id": POOR_USER_ID})
        assert u["wallet_balance"] == 1.0

    def test_real_call_returns_suggestions(self, admin, grammar_chat, mongo):
        """Single real Claude call for the whole module."""
        fields = {
            "ada_parsel": "1234/56",
            "adres": "ıstanbul ili kadıköy ilçesi, gayrımenkul caddesi no 12",
            "oda_sayisi": "3+1",
            "isitma": "kombi ısıtma sistemi mevcuttur ve  çalişmaktadir",
        }
        p = admin.patch(f"{API}/chats/{grammar_chat}/fields", json={"fields": fields})
        assert p.status_code == 200, p.text

        before = mongo.users.find_one({"user_id": "user_grelligram_seed"})["wallet_balance"]
        r = admin.post(f"{API}/chats/{grammar_chat}/grammar-check", timeout=180)
        assert r.status_code == 200, r.text
        d = r.json()
        assert set(["suggestions", "tokens", "cost_try", "wallet_balance"]).issubset(d.keys())
        assert isinstance(d["suggestions"], list)
        assert d["tokens"]["input"] > 0, f"no input tokens counted: {d}"
        assert d["tokens"]["output"] > 0, f"no output tokens counted: {d}"
        assert d["cost_try"] > 0
        for s in d["suggestions"]:
            assert isinstance(s, dict)
            for k in ("field", "original", "corrected", "reason"):
                assert k in s, f"suggestion missing '{k}': {s}"
        after = mongo.users.find_one({"user_id": "user_grelligram_seed"})["wallet_balance"]
        assert round(before - after, 2) == round(d["cost_try"], 2), (before, after, d["cost_try"])
        assert round(after, 2) == d["wallet_balance"]
        TestGrammarCheck.last = d

    def test_usage_events_written(self, mongo, grammar_chat):
        ev = mongo.usage_events.find_one({"chat_id": grammar_chat, "mode": "grammar"})
        assert ev is not None, "no usage_events row for grammar check"
        assert ev["input_tokens"] > 0
        assert ev["output_tokens"] > 0
        assert ev["cost"] > 0
        assert ev["user_id"] == "user_grelligram_seed"
        assert "actual_ai_cost_usd" in ev and "created_at" in ev


# ================================================== GET /api/chats/{id}/download/udf
KONUT_VALUES = {
    "ada_parsel": "TEST_1234 / 56",
    "adres": "Bağdat Caddesi No 120, Kadıköy, İstanbul",
    "brut_alan": "145",
    "net_alan": "128",
    "oda_sayisi": "3+1",
    "bina_yasi": "12",
    "kat": "4. Kat",
    "isitma": "Doğalgaz Kombi",
    "cevre_ozellikleri": "Metro, okul, hastane ve park yakınında",
    "emsal_fiyat": "78500",
}
KONUT_LABELS = {
    "ada_parsel": "Ada / Parsel No",
    "adres": "Açık Adres",
    "brut_alan": "Brüt Alan (m²)",
    "net_alan": "Net Alan (m²)",
    "oda_sayisi": "Oda Sayısı (Ör. 3+1)",
    "bina_yasi": "Bina Yaşı",
    "kat": "Bulunduğu Kat",
    "isitma": "Isıtma Sistemi",
    "cevre_ozellikleri": "Çevre / Sosyal Donatılar",
    "emsal_fiyat": "Emsal Birim Fiyat (TL/m²)",
}


@pytest.fixture(scope="module")
def udf_chat(admin, state):
    r = admin.post(f"{API}/chats", json={"mode": "report", "template_id": "konut"})
    assert r.status_code == 200, r.text
    cid = r.json()["chat"]["chat_id"]
    state["chats"].append(cid)
    p = admin.patch(f"{API}/chats/{cid}/fields", json={"fields": KONUT_VALUES})
    assert p.status_code == 200, p.text
    return cid


@pytest.fixture(scope="module")
def udf_response(admin, udf_chat):
    r = admin.get(f"{API}/chats/{udf_chat}/download/udf", timeout=60)
    assert r.status_code == 200, r.text[:400]
    return r


@pytest.fixture(scope="module")
def content_xml(udf_response):
    z = zipfile.ZipFile(io.BytesIO(udf_response.content))
    return z.read("content.xml").decode("utf-8")


def _cdata(xml: str) -> str:
    m = re.search(r"<content><!\[CDATA\[(.*?)\]\]></content>", xml, re.S)
    assert m, "CDATA content block missing"
    return m.group(1)


class TestUDFExport:
    def test_udf_download_produces_valid_zip(self, udf_response):
        cd = udf_response.headers.get("content-disposition", "")
        assert ".udf" in cd, cd
        buf = io.BytesIO(udf_response.content)
        assert zipfile.is_zipfile(buf), "response body is not a ZIP archive"
        z = zipfile.ZipFile(buf)
        assert z.testzip() is None
        assert "content.xml" in z.namelist(), z.namelist()
        assert len(z.read("content.xml")) > 100

    def test_udf_xml_structure(self, content_xml):
        assert content_xml.startswith('<?xml version="1.0"')
        assert re.search(r"<template\s+format_id=\"[^\"]+\"\s*>", content_xml)
        assert "<content><![CDATA[" in content_xml
        assert "<properties>" in content_xml and "<pageFormat" in content_xml
        assert '<elements resolver="hvl-oluster">' in content_xml
        assert content_xml.rstrip().endswith("</template>")
        paras = re.findall(r"<paragraph[^>]*>.*?</paragraph>", content_xml, re.S)
        assert len(paras) > 5, f"too few paragraphs: {len(paras)}"
        for p in paras:
            assert re.search(r"<content startOffset=\"\d+\" length=\"\d+\"[^>]*/>", p), p
        # XML must be parseable
        import xml.etree.ElementTree as ET
        root = ET.fromstring(content_xml)
        assert root.tag == "template"

    def test_udf_contains_field_values(self, content_xml):
        body = _cdata(content_xml)
        assert "Konut Değerleme Raporu" in body
        assert "GAYRİMENKUL BİLGİLERİ" in body
        for key, val in KONUT_VALUES.items():
            label = KONUT_LABELS[key]
            assert f"{label}: {val}" in body, f"missing '{label}: {val}' in UDF body"

    def test_udf_offsets_valid(self, content_xml):
        body = _cdata(content_xml)
        pairs = [(int(a), int(b)) for a, b in
                 re.findall(r'<content startOffset="(\d+)" length="(\d+)"', content_xml)]
        assert pairs
        cursor = 0
        for start, length in pairs:
            assert start == cursor, f"non-contiguous offsets at {start}, expected {cursor}"
            cursor = start + length
        assert cursor == len(body), (
            f"offset total {cursor} != CDATA length {len(body)} "
            "(last paragraph length overruns the content buffer)")

    def test_udf_bold_heuristic(self, content_xml):
        body = _cdata(content_xml)
        lines = body.split("\n")
        pairs = [(int(a), int(b), bold) for a, b, bold in re.findall(
            r'<content startOffset="(\d+)" length="(\d+)"[^>]*bold="(true|false)"', content_xml)]
        assert len(pairs) == len(lines), (len(pairs), len(lines))
        bold_by_line = {lines[i]: pairs[i][2] for i in range(len(lines))}
        assert bold_by_line.get("Konut Değerleme Raporu") == "true"
        assert bold_by_line.get("GAYRİMENKUL BİLGİLERİ") == "true"
        assert bold_by_line.get("Ada / Parsel No: TEST_1234 / 56") == "false"

    def test_invalid_format_400(self, admin, udf_chat):
        r = admin.get(f"{API}/chats/{udf_chat}/download/xyz")
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Format must be pdf, docx or udf"

    def test_udf_other_user_cannot_download(self, user_client, udf_chat):
        r = user_client.get(f"{API}/chats/{udf_chat}/download/udf")
        assert r.status_code == 404, r.text

    def test_pdf_docx_regression(self, admin, udf_chat):
        for fmt, sig in (("pdf", b"%PDF"), ("docx", b"PK")):
            r = admin.get(f"{API}/chats/{udf_chat}/download/{fmt}", timeout=60)
            assert r.status_code == 200, r.text[:300]
            assert r.content.startswith(sig), fmt
