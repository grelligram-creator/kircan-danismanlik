"""Main FastAPI backend for Real Estate Valuation AI Chat."""
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, UploadFile, File, Form, Cookie, Header, Depends
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime, timezone, timedelta
import os
import re
import uuid
import shutil
import json
import logging
import asyncio
import httpx

from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType, TextDelta, StreamDone
from emergentintegrations.payments.stripe.checkout import (
    StripeCheckout, CheckoutSessionRequest, CheckoutStatusResponse,
)

from templates_data import REPORT_TEMPLATES, FAQ_ITEMS
from document_utils import parse_uploaded_file, generate_pdf, generate_docx
from wallet_packages import WALLET_PACKAGES, get_package

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

UPLOAD_DIR = ROOT_DIR / "uploads"
REPORTS_DIR = ROOT_DIR / "generated_reports"
UPLOAD_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')
STRIPE_API_KEY = os.environ.get('STRIPE_API_KEY', 'sk_test_emergent')

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

app = FastAPI()
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# Models
# ============================================================

class User(BaseModel):
    user_id: str
    email: str
    name: str
    picture: str = ""
    wallet_balance: float = 50.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatSession(BaseModel):
    chat_id: str
    user_id: str
    title: str = "Yeni Sohbet"
    mode: str = "report"  # 'report' | 'faq'
    template_id: Optional[str] = None
    template_name: Optional[str] = None
    fields: Dict[str, Any] = Field(default_factory=dict)
    sections: Dict[str, str] = Field(default_factory=dict)
    status: str = "in_progress"  # 'in_progress' | 'completed'
    report_no: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatMessage(BaseModel):
    message_id: str
    chat_id: str
    role: str  # 'user' | 'assistant' | 'system'
    content: str
    attachments: List[Dict[str, str]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# Auth Helpers
# ============================================================

async def get_current_user(
    session_token: Optional[str] = Cookie(default=None),
    authorization: Optional[str] = Header(default=None),
) -> User:
    token = session_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session_doc = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session_doc:
        raise HTTPException(status_code=401, detail="Invalid session")

    expires_at = session_doc.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")

    user_doc = await db.users.find_one({"user_id": session_doc["user_id"]}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=401, detail="User not found")

    # normalize created_at & backfill legacy credits->wallet_balance
    if isinstance(user_doc.get("created_at"), str):
        user_doc["created_at"] = datetime.fromisoformat(user_doc["created_at"])
    if "wallet_balance" not in user_doc:
        legacy_credits = user_doc.get("credits", 0)
        user_doc["wallet_balance"] = float(legacy_credits) if legacy_credits else 50.0
        await db.users.update_one(
            {"user_id": user_doc["user_id"]},
            {"$set": {"wallet_balance": user_doc["wallet_balance"]}, "$unset": {"credits": ""}},
        )
    user_doc.pop("credits", None)
    return User(**user_doc)


# ============================================================
# Auth Routes
# ============================================================

@api.post("/auth/session")
async def create_session(payload: Dict[str, str], response: Response):
    """Exchange Emergent session_id for a persistent session_token."""
    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    async with httpx.AsyncClient(timeout=15) as hx:
        r = await hx.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": session_id},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Session validation failed")
    data = r.json()

    email = data["email"]
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"name": data.get("name", existing.get("name", "")),
                      "picture": data.get("picture", existing.get("picture", ""))}},
        )
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id,
            "email": email,
            "name": data.get("name", ""),
            "picture": data.get("picture", ""),
            "wallet_balance": 50.0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    session_token = data["session_token"]
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc),
    })

    response.set_cookie(
        key="session_token", value=session_token,
        httponly=True, secure=True, samesite="none", path="/",
        max_age=7 * 24 * 60 * 60,
    )
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return {"user": user_doc}


@api.get("/auth/me")
async def auth_me(user: User = Depends(get_current_user)):
    return user.model_dump()


@api.post("/auth/logout")
async def logout(response: Response, session_token: Optional[str] = Cookie(default=None)):
    if session_token:
        await db.user_sessions.delete_one({"session_token": session_token})
    response.delete_cookie("session_token", path="/")
    return {"success": True}


# ============================================================
# Templates & FAQ
# ============================================================

@api.get("/templates")
async def list_templates(user: User = Depends(get_current_user)):
    """Return built-in templates + user's own custom templates + shared-with-user templates."""
    q = {"$or": [{"user_id": user.user_id}, {"shared_with": {"$in": [user.email, user.email.lower()]}}]}
    custom_cursor = db.user_templates.find(q, {"_id": 0}).sort("created_at", -1)
    custom = await custom_cursor.to_list(200)
    for c in custom:
        c.pop("original_docx_path", None)
        c.pop("prepared_docx_path", None)
        c["is_shared_with_me"] = c.get("user_id") != user.user_id
    return {"templates": REPORT_TEMPLATES, "custom_templates": custom}


@api.get("/faq")
async def list_faq():
    return {"items": FAQ_ITEMS}


# ============================================================
# User Templates (custom DOCX with AI-detected placeholders)
# ============================================================

from template_utils import (
    extract_document_map, detect_placeholders_via_llm,
    apply_placeholders, render_docx, docx_to_html, preview_html,
)

TEMPLATES_DIR = ROOT_DIR / "user_templates"
TEMPLATES_DIR.mkdir(exist_ok=True)


async def _claude_call(system: str, user_text: str) -> str:
    llm = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"tpl_detect_{uuid.uuid4().hex[:8]}",
        system_message=system,
    ).with_model("anthropic", "claude-sonnet-5")
    resp = await llm.send_message(UserMessage(text=user_text))
    return resp.content if hasattr(resp, "content") else str(resp)


async def _get_user_template(tid: str) -> Optional[Dict[str, Any]]:
    return await db.user_templates.find_one({"template_id": tid}, {"_id": 0})


@api.post("/user_templates/upload")
async def upload_user_template(
    file: UploadFile = File(...),
    name: str = Form(...),
    description: str = Form(""),
    user: User = Depends(get_current_user),
):
    """Upload a .docx template. Backend AI-detects placeholders and prepares a Jinja-tokenized copy."""
    if not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Sadece .docx dosyaları desteklenir")

    tid = f"utpl_{uuid.uuid4().hex[:12]}"
    tdir = TEMPLATES_DIR / tid
    tdir.mkdir(parents=True, exist_ok=True)
    original_path = tdir / "original.docx"
    prepared_path = tdir / "prepared.docx"
    content = await file.read()
    original_path.write_bytes(content)

    # 1. extract structure
    doc_map = extract_document_map(str(original_path))
    # 2. detect placeholders via Claude
    try:
        fields = await detect_placeholders_via_llm(doc_map, _claude_call)
    except Exception as e:
        logger.exception("Placeholder detection failed")
        raise HTTPException(status_code=500, detail=f"AI tespit hatası: {e}")
    # 3. inject Jinja tokens into a prepared copy
    summary = apply_placeholders(str(original_path), str(prepared_path), fields)

    doc_record = {
        "template_id": tid,
        "user_id": user.user_id,
        "name": name.strip() or file.filename,
        "description": description.strip(),
        "filename": file.filename,
        "original_docx_path": str(original_path),
        "prepared_docx_path": str(prepared_path),
        "fields": fields,
        "detection_summary": summary,
        "kind": "user",
        "cost_per_message": 5.0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.user_templates.insert_one(doc_record)
    doc_record.pop("_id", None)
    return {
        "template": {
            **{k: v for k, v in doc_record.items() if k not in ("original_docx_path", "prepared_docx_path")},
        },
    }


@api.get("/user_templates")
async def list_user_templates(user: User = Depends(get_current_user)):
    q = {"$or": [{"user_id": user.user_id}, {"shared_with": {"$in": [user.email, user.email.lower()]}}]}
    cursor = db.user_templates.find(q, {"_id": 0, "original_docx_path": 0, "prepared_docx_path": 0}).sort("created_at", -1)
    items = await cursor.to_list(500)
    for c in items:
        c["is_shared_with_me"] = c.get("user_id") != user.user_id
    return {"templates": items}


@api.get("/user_templates/{tid}")
async def get_user_template(tid: str, user: User = Depends(get_current_user)):
    t = await _get_user_template(tid)
    if not t or not _template_visible_to(t, user):
        raise HTTPException(status_code=404, detail="Template not found")
    t.pop("original_docx_path", None)
    t.pop("prepared_docx_path", None)
    t["is_shared_with_me"] = t.get("user_id") != user.user_id
    return t


@api.post("/user_templates/{tid}/share")
async def share_user_template(tid: str, payload: Dict[str, Any], user: User = Depends(get_current_user)):
    """Owner-only: add/remove team member emails."""
    t = await _get_user_template(tid)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    if t.get("user_id") != user.user_id:
        raise HTTPException(status_code=403, detail="Sadece sahibi paylaşımı düzenleyebilir")
    add_emails = [str(e).strip().lower() for e in (payload.get("add") or []) if e]
    remove_emails = [str(e).strip().lower() for e in (payload.get("remove") or []) if e]
    current = [e.lower() for e in (t.get("shared_with") or [])]
    for e in add_emails:
        if e and e not in current and e != user.email.lower():
            current.append(e)
    current = [e for e in current if e not in remove_emails]
    await db.user_templates.update_one({"template_id": tid}, {"$set": {"shared_with": current}})
    return {"shared_with": current}


@api.get("/user_templates/{tid}/versions")
async def list_template_versions(tid: str, user: User = Depends(get_current_user)):
    t = await _get_user_template(tid)
    if not t or t.get("user_id") != user.user_id:
        raise HTTPException(status_code=404, detail="Template not found")
    cursor = db.template_versions.find(
        {"template_id": tid},
        {"_id": 0, "prepared_snapshot_path": 0},
    ).sort("created_at", -1).limit(50)
    versions = await cursor.to_list(50)
    return {"versions": versions}


@api.post("/user_templates/{tid}/versions/{vid}/restore")
async def restore_template_version(tid: str, vid: str, user: User = Depends(get_current_user)):
    t = await _get_user_template(tid)
    if not t or t.get("user_id") != user.user_id:
        raise HTTPException(status_code=404, detail="Template not found")
    v = await db.template_versions.find_one({"template_id": tid, "version_id": vid}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Version not found")

    # Save a "pre-restore" snapshot so restore itself is undoable
    current_ver = {
        "version_id": f"ver_{uuid.uuid4().hex[:10]}",
        "template_id": tid, "user_id": user.user_id,
        "name": t.get("name"), "description": t.get("description"),
        "fields": t.get("fields", []), "detection_summary": t.get("detection_summary"),
        "note": f"Auto-snapshot before restoring {vid}",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    src_prep = Path(t["prepared_docx_path"])
    if src_prep.exists():
        snap = src_prep.parent / f"prepared_{current_ver['version_id']}.docx"
        try:
            shutil.copy2(str(src_prep), str(snap))
            current_ver["prepared_snapshot_path"] = str(snap)
        except Exception:
            pass
    await db.template_versions.insert_one(current_ver)

    # Restore fields + rebuild prepared.docx from original + those fields
    fields = v.get("fields", [])
    summary = apply_placeholders(t["original_docx_path"], t["prepared_docx_path"], fields)
    await db.user_templates.update_one(
        {"template_id": tid},
        {"$set": {
            "name": v.get("name") or t["name"],
            "description": v.get("description") or t.get("description", ""),
            "fields": fields,
            "detection_summary": summary,
        }},
    )
    updated = await _get_user_template(tid)
    updated.pop("original_docx_path", None)
    updated.pop("prepared_docx_path", None)
    return updated


@api.patch("/user_templates/{tid}")
async def update_user_template(tid: str, payload: Dict[str, Any], user: User = Depends(get_current_user)):
    t = await _get_user_template(tid)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    if t.get("user_id") != user.user_id:
        raise HTTPException(status_code=403, detail="Yalnızca sahibi düzenleyebilir")

    # Snapshot current state before we mutate
    version = {
        "version_id": f"ver_{uuid.uuid4().hex[:10]}",
        "template_id": tid,
        "user_id": user.user_id,
        "name": t.get("name"),
        "description": t.get("description"),
        "fields": t.get("fields", []),
        "detection_summary": t.get("detection_summary"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # Save prepared.docx snapshot next to it
    src_prep = Path(t["prepared_docx_path"])
    if src_prep.exists():
        snap_path = src_prep.parent / f"prepared_{version['version_id']}.docx"
        try:
            shutil.copy2(str(src_prep), str(snap_path))
            version["prepared_snapshot_path"] = str(snap_path)
        except Exception:
            pass
    await db.template_versions.insert_one(version)
    updates: Dict[str, Any] = {}
    if "name" in payload:
        updates["name"] = str(payload["name"]).strip()
    if "description" in payload:
        updates["description"] = str(payload["description"]).strip()
    if "fields" in payload and isinstance(payload["fields"], list):
        clean_fields: List[Dict[str, Any]] = []
        for f in payload["fields"]:
            key = str(f.get("key", "")).strip()
            key = re.sub(r"[^a-z0-9_]", "_", key.lower())
            if not key:
                continue
            ftype = f.get("type") if f.get("type") in ("text", "number", "date", "textarea", "image", "table") else "text"
            entry: Dict[str, Any] = {
                "key": key,
                "label": str(f.get("label", key)).strip() or key,
                "type": ftype,
                "node_id": f.get("node_id"),
                "replace_text": f.get("replace_text"),
                "append_after_label": f.get("append_after_label"),
                "hint": f.get("hint", ""),
            }
            if ftype == "table":
                cols: List[Dict[str, Any]] = []
                col_keys_seen = set()
                for c in (f.get("columns") or []):
                    ck = re.sub(r"[^a-z0-9_]", "_", str(c.get("key", "")).lower()).strip("_")
                    if not ck or ck in col_keys_seen:
                        continue
                    col_keys_seen.add(ck)
                    cols.append({
                        "key": ck,
                        "label": str(c.get("label", ck)).strip() or ck,
                        "type": c.get("type") if c.get("type") in ("text", "number", "date") else "text",
                    })
                entry["columns"] = cols
                entry["header_row_index"] = int(f.get("header_row_index", 0) or 0)
                entry["template_row_index"] = int(f.get("template_row_index", 1) or 1)
            clean_fields.append(entry)
        updates["fields"] = clean_fields
        # Re-apply placeholders on the original to rebuild prepared.docx
        summary = apply_placeholders(t["original_docx_path"], t["prepared_docx_path"], clean_fields)
        updates["detection_summary"] = summary
    if updates:
        await db.user_templates.update_one({"template_id": tid}, {"$set": updates})
    updated = await _get_user_template(tid)
    updated.pop("original_docx_path", None)
    updated.pop("prepared_docx_path", None)
    return updated


@api.delete("/user_templates/{tid}")
async def delete_user_template(tid: str, user: User = Depends(get_current_user)):
    t = await _get_user_template(tid)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    if t.get("user_id") != user.user_id:
        raise HTTPException(status_code=403, detail="Yalnızca sahibi silebilir")
    tdir = Path(t["original_docx_path"]).parent
    try:
        shutil.rmtree(tdir, ignore_errors=True)
    except Exception:
        pass
    await db.user_templates.delete_one({"template_id": tid})
    return {"success": True}


def _template_visible_to(tpl: Dict[str, Any], user: User) -> bool:
    """Owner OR user's email is listed in shared_with (case-insensitive)."""
    if tpl.get("user_id") == user.user_id:
        return True
    shared = [e.lower() for e in (tpl.get("shared_with") or [])]
    return user.email.lower() in shared


@api.get("/user_templates/{tid}/preview")
async def user_template_preview(tid: str, chat_id: Optional[str] = None, user: User = Depends(get_current_user)):
    """Return HTML preview. If chat_id given, substitute the chat's current field values."""
    t = await _get_user_template(tid)
    if not t or not _template_visible_to(t, user):
        raise HTTPException(status_code=404, detail="Template not found")
    values: Dict[str, Any] = {}
    image_urls: Dict[str, Any] = {}
    table_data: Dict[str, List[Dict[str, Any]]] = {}
    if chat_id:
        chat = await db.chats.find_one({"chat_id": chat_id, "user_id": user.user_id}, {"_id": 0})
        if chat:
            values = dict(chat.get("fields", {}))
            for k, v in list(values.items()):
                if isinstance(v, dict) and v.get("__image__"):
                    image_urls[k] = {
                        "preview_url": v.get("preview_url", ""),
                        "width_mm": v.get("width_mm", 80),
                    }
                    values.pop(k, None)
                elif isinstance(v, list):
                    table_data[k] = v
                    values.pop(k, None)
    html = preview_html(t["prepared_docx_path"], values, image_urls, table_data)
    return {"html": html, "fields": t.get("fields", [])}


# ============================================================
# Chat Sessions
# ============================================================

def _template_by_id(tid: str) -> Optional[Dict[str, Any]]:
    return next((t for t in REPORT_TEMPLATES if t["id"] == tid), None)


async def _resolve_template(template_id: Optional[str], user_template_id: Optional[str], user: User) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Return (builtin_template, user_template). Only one is non-null. User templates must be owned by or shared with user."""
    if user_template_id:
        ut = await _get_user_template(user_template_id)
        if ut and not _template_visible_to(ut, user):
            return None, None
        return None, ut
    if template_id:
        return _template_by_id(template_id), None
    return None, None


@api.get("/chats")
async def list_chats(user: User = Depends(get_current_user)):
    cursor = db.chats.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).limit(50)
    chats = await cursor.to_list(50)
    for c in chats:
        if isinstance(c.get("created_at"), str):
            c["created_at"] = datetime.fromisoformat(c["created_at"])
    return {"chats": chats}


@api.post("/chats")
async def create_chat(payload: Dict[str, Any], user: User = Depends(get_current_user)):
    mode = payload.get("mode", "report")
    template_id = payload.get("template_id")
    user_template_id = payload.get("user_template_id")
    builtin, user_tpl = await _resolve_template(template_id, user_template_id, user)
    # ACL: if user requested a user_template_id but it's not visible to them, reject
    if user_template_id and not user_tpl:
        raise HTTPException(status_code=404, detail="Template not found")

    chat_id = f"chat_{uuid.uuid4().hex[:10]}"
    if mode == "faq":
        title = "FAQ Sohbeti"
    elif user_tpl:
        title = user_tpl["name"]
    elif builtin:
        title = builtin["name"]
    else:
        title = "Yeni Rapor"

    chat_doc = {
        "chat_id": chat_id,
        "user_id": user.user_id,
        "title": title,
        "mode": mode,
        "template_id": template_id,
        "user_template_id": user_template_id,
        "template_name": user_tpl["name"] if user_tpl else (builtin["name"] if builtin else None),
        "fields": {},
        "sections": {},
        "status": "in_progress",
        "report_no": f"VAL-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}" if mode == "report" else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.chats.insert_one(chat_doc)
    chat_doc.pop("_id", None)

    # Seed system + first assistant message
    if mode == "report" and user_tpl and user_tpl.get("fields"):
        first = user_tpl["fields"][0]
        greeting = (
            f"Merhaba! **{user_tpl['name']}** hazırlamanıza yardımcı olacağım.\n\n"
            f"Bu şablonda **{len(user_tpl['fields'])} alan** tespit edildi. Size sırayla soracağım ve raporu adım adım dolduracağız.\n\n"
            f"Başlayalım — **{first['label']}** bilgisini paylaşır mısınız?"
            + (f"\n\n_{first.get('hint','')}_" if first.get("hint") else "")
        )
    elif mode == "report" and builtin:
        greeting = (
            f"Merhaba! **{builtin['name']}** hazırlamanıza yardımcı olacağım. "
            f"Size gerekli bilgileri sırayla soracağım ve raporu adım adım dolduracağız.\n\n"
            f"Başlayalım — **{builtin['fields'][0]['label']}** bilgisini paylaşır mısınız?\n\n"
            f"Ayrıca ilgili PDF/Word/Excel dosyalarınızı yükleyerek bilgileri otomatik olarak çıkarmama yardımcı olabilirsiniz."
        )
    else:
        greeting = (
            "Merhaba! Gayrimenkul değerleme hakkında merak ettiğiniz teknik soruları sorabilirsiniz. "
            "Emsal karşılaştırma, kapitalizasyon oranı, SPK mevzuatı, amortisman hesabı gibi konularda yardımcı olabilirim."
        )

    msg = {
        "message_id": f"msg_{uuid.uuid4().hex[:10]}",
        "chat_id": chat_id,
        "role": "assistant",
        "content": greeting,
        "attachments": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.messages.insert_one(msg)
    msg.pop("_id", None)
    chat_doc["created_at"] = datetime.fromisoformat(chat_doc["created_at"])
    return {"chat": chat_doc, "message": msg}


@api.get("/chats/{chat_id}")
async def get_chat(chat_id: str, user: User = Depends(get_current_user)):
    chat = await db.chats.find_one({"chat_id": chat_id, "user_id": user.user_id}, {"_id": 0})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    msgs = await db.messages.find({"chat_id": chat_id}, {"_id": 0}).sort("created_at", 1).to_list(500)
    return {"chat": chat, "messages": msgs}


@api.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, user: User = Depends(get_current_user)):
    await db.chats.delete_one({"chat_id": chat_id, "user_id": user.user_id})
    await db.messages.delete_many({"chat_id": chat_id})
    return {"success": True}


# ============================================================
# Chat Messaging (Claude Sonnet 5)
# ============================================================

def _build_system_prompt(chat: Dict[str, Any], user_tpl: Optional[Dict[str, Any]] = None) -> str:
    if chat["mode"] == "faq":
        faq_text = "\n\n".join([f"S: {q['q']}\nC: {q['a']}" for q in FAQ_ITEMS])
        return (
            "Sen deneyimli, SPK lisanslı bir gayrimenkul değerleme uzmanısın. "
            "Türkçe, net ve teknik olarak doğru cevaplar ver. "
            "Aşağıdaki bilgi bankasından yararlanabilirsin ancak dışına da çıkabilirsin:\n\n"
            + faq_text
        )

    if user_tpl:
        fields_json = json.dumps(
            [{"key": f["key"], "label": f["label"], "type": f["type"], "hint": f.get("hint", ""),
              "columns": f.get("columns")} for f in user_tpl["fields"]],
            ensure_ascii=False, indent=2,
        )
        collected = json.dumps(chat.get("fields", {}), ensure_ascii=False, indent=2, default=str)
        return f"""Sen deneyimli, SPK lisanslı bir gayrimenkul değerleme uzmanısın. Kullanıcının **{user_tpl['name']}** şablonunu doldurmasına yardım ediyorsun.

## Görevin
1. Aşağıdaki alanları SIRAYLA, tek tek kullanıcıya sor ve topla.
2. `image` tipindeki alanlar için kullanıcıdan üstteki "Görsel Slotları" barından fotoğraf yüklemesini iste (değer olarak "__pending__" kaydet).
3. `table` tipindeki alanlar için: önce kaç satır gireceğini sor, sonra her satırın sütunlarını sırayla topla. Değeri liste formatında ver: `[{{ "col_key1": "...", "col_key2": "..." }}, ...]`.
4. PDF/Excel/Word yüklendiğinde içeriğinden değerleri çıkar.
5. Her cevabından SONRA JSON blok döndür: en sonda `<!--UPDATE-->` etiketi ile birlikte:
   `<!--UPDATE {{"fields": {{"kisi": "Ali", "emsaller": [{{"adres":"X","alan":100}}] }} }}-->`
6. Tüm alanlar dolduğunda "Rapor tamamlandı" yaz ve `<!--UPDATE {{...status:'completed'}}-->` işaretle.

## Toplanacak Alanlar (JSON şema)
{fields_json}

## Şu ana kadar toplanan bilgiler
{collected}

## Kurallar
- Kısa, net ve profesyonel bir dille yaz.
- Her cevabın sonunda MUTLAKA `<!--UPDATE {{...}}-->` etiketi olsun.
- Kullanıcı ilgisiz bir şey sorarsa nazikçe rapor akışına geri getir."""

    template = _template_by_id(chat.get("template_id", ""))
    if not template:
        return "Sen bir gayrimenkul değerleme uzmanısın."

    fields_json = json.dumps(template["fields"], ensure_ascii=False, indent=2)
    sections_list = "\n".join(f"- {s}" for s in template["sections"])
    collected = json.dumps(chat.get("fields", {}), ensure_ascii=False, indent=2)

    return f"""Sen deneyimli, SPK lisanslı bir gayrimenkul değerleme uzmanısın. Kullanıcının **{template['name']}** hazırlamasına yardım ediyorsun.

## Görevin
1. Aşağıdaki alanları sırayla, tek tek, kullanıcıya sor ve topla.
2. Kullanıcı PDF/Excel/Word yüklediğinde içeriğinden değerleri çıkar.
3. Her cevabından sonra JSON blok döndür: en sonda `<!--UPDATE-->` etiketi ile birlikte:
   `<!--UPDATE {{"fields": {{...toplanan_alanlar...}}, "sections": {{"Bölüm Adı":"içerik metni"}} }}-->`
4. Tüm alanlar dolduğunda sırasıyla her rapor bölümü için profesyonel Türkçe metin üret ve sections içine yaz.
5. Değerleme sonuç bölümünde, toplanan verileri kullanarak makul ve gerekçeli bir değer tahmini sun.

## Toplanacak Alanlar (JSON şema)
{fields_json}

## Rapor Bölümleri (sırayla üret)
{sections_list}

## Şu ana kadar toplanan bilgiler
{collected}

## Kurallar
- Kısa, net ve profesyonel bir dille yaz.
- Her cevabın sonunda MUTLAKA `<!--UPDATE {{...}}-->` etiketi olsun (kullanıcı bunu göremez, sistem güncelleme için kullanır).
- Kullanıcı ilgisiz bir şey sorarsa nazikçe rapor akışına geri getir.
- Tüm alanlar dolduğunda: "Rapor tamamlandı" ifadesini kullan ve `<!--UPDATE ... status:'completed'-->` işaretle."""


def _extract_update(text: str) -> tuple[str, Optional[Dict[str, Any]]]:
    """Extract <!--UPDATE {...}--> from assistant text, return (clean_text, update_dict)."""
    marker_start = text.find("<!--UPDATE")
    if marker_start == -1:
        return text, None
    marker_end = text.find("-->", marker_start)
    if marker_end == -1:
        return text, None
    raw = text[marker_start + len("<!--UPDATE"):marker_end].strip()
    clean = (text[:marker_start] + text[marker_end + 3:]).strip()
    try:
        update = json.loads(raw)
        return clean, update
    except Exception:
        return clean, None


def _cost_for_chat(chat: Dict[str, Any]) -> float:
    if chat["mode"] == "faq":
        return 2.0
    if chat.get("user_template_id"):
        return 5.0
    tpl = _template_by_id(chat.get("template_id", "")) if chat.get("template_id") else None
    return float(tpl["cost_per_message"]) if tpl else 5.0


@api.post("/chats/{chat_id}/message")
async def send_message(
    chat_id: str,
    payload: Dict[str, Any],
    user: User = Depends(get_current_user),
):
    """SSE streaming endpoint. Streams `delta` events, then a final `done` event."""
    chat = await db.chats.find_one({"chat_id": chat_id, "user_id": user.user_id}, {"_id": 0})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    cost = _cost_for_chat(chat)
    # Atomically reserve funds up-front (prevents race + revenue leak on client disconnect).
    # We only charge if the current balance can cover the cost; otherwise return 402.
    reserved = await db.users.find_one_and_update(
        {"user_id": user.user_id, "wallet_balance": {"$gte": cost}},
        {"$inc": {"wallet_balance": -cost}},
        return_document=True,
    )
    if not reserved:
        raise HTTPException(
            status_code=402,
            detail={"error": "insufficient_balance", "required": cost, "balance": user.wallet_balance},
        )
    new_balance = round(float(reserved.get("wallet_balance", 0.0)), 2)

    # Ledger: log this usage for analytics (deducted regardless of stream outcome — reserved above)
    await db.usage_events.insert_one({
        "user_id": user.user_id,
        "chat_id": chat_id,
        "mode": chat["mode"],
        "template_id": chat.get("template_id"),
        "template_name": chat.get("template_name"),
        "cost": float(cost),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    user_text = (payload.get("content") or "").strip()
    attachment_ids: List[str] = payload.get("attachment_ids", [])

    user_msg = {
        "message_id": f"msg_{uuid.uuid4().hex[:10]}",
        "chat_id": chat_id,
        "role": "user",
        "content": user_text,
        "attachments": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    history = await db.messages.find({"chat_id": chat_id}, {"_id": 0}).sort("created_at", 1).to_list(500)

    attachment_texts = []
    for aid in attachment_ids:
        att = await db.uploads.find_one({"upload_id": aid, "user_id": user.user_id}, {"_id": 0})
        if att:
            content = parse_uploaded_file(att["path"])
            attachment_texts.append(f"[Yüklenen dosya: {att['filename']}]\n{content[:8000]}")
            user_msg["attachments"].append({"upload_id": aid, "filename": att["filename"]})

    await db.messages.insert_one(user_msg)
    user_msg.pop("_id", None)

    system_prompt = _build_system_prompt(chat, user_tpl=(await _get_user_template(chat["user_template_id"])) if chat.get("user_template_id") else None)
    llm = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=chat_id,
        system_message=system_prompt,
    ).with_model("anthropic", "claude-sonnet-5")

    context_lines: List[str] = []
    for m in history[-20:]:
        if m["role"] == "user":
            context_lines.append(f"Kullanıcı: {m['content']}")
        elif m["role"] == "assistant":
            clean, _ = _extract_update(m["content"])
            context_lines.append(f"Asistan: {clean}")
    context_str = "\n\n".join(context_lines)

    full_prompt = user_text or "(Ekli dosyaları analiz et)"
    if attachment_texts:
        full_prompt = full_prompt + "\n\n" + "\n\n".join(attachment_texts)
    if context_str:
        full_prompt = f"[Önceki konuşma]\n{context_str}\n\n[Yeni mesaj]\n{full_prompt}"

    async def event_generator():
        # first event: user message echo (so frontend can render it immediately)
        yield f"data: {json.dumps({'type': 'user_message', 'message': user_msg}, default=str)}\n\n"

        full_text_parts: List[str] = []
        try:
            async for event in llm.stream_message(UserMessage(text=full_prompt)):
                if isinstance(event, TextDelta):
                    full_text_parts.append(event.content)
                    # stream raw text so UI can accumulate; UI strips <!--UPDATE ...--> markers.
                    yield f"data: {json.dumps({'type': 'delta', 'content': event.content})}\n\n"
                elif isinstance(event, StreamDone):
                    break
        except Exception as e:
            logger.exception("LLM stream error")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        assistant_text = "".join(full_text_parts)
        clean_text, update = _extract_update(assistant_text)

        assistant_msg = {
            "message_id": f"msg_{uuid.uuid4().hex[:10]}",
            "chat_id": chat_id,
            "role": "assistant",
            "content": clean_text,
            "attachments": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.messages.insert_one(assistant_msg)
        assistant_msg.pop("_id", None)

        # Apply updates
        new_fields = dict(chat.get("fields", {}))
        new_sections = dict(chat.get("sections", {}))
        new_status = chat.get("status", "in_progress")
        if update:
            if isinstance(update.get("fields"), dict):
                new_fields.update({k: v for k, v in update["fields"].items() if v not in (None, "")})
            if isinstance(update.get("sections"), dict):
                new_sections.update({k: v for k, v in update["sections"].items() if v})
            if update.get("status") == "completed":
                new_status = "completed"

        tpl = _template_by_id(chat.get("template_id", "")) if chat.get("template_id") else None
        user_tpl_now = await _get_user_template(chat["user_template_id"]) if chat.get("user_template_id") else None
        if tpl:
            all_fields_done = all(k in new_fields and new_fields[k] not in (None, "")
                                   for k in [f["key"] for f in tpl["fields"]])
            all_sections_done = all(s in new_sections and new_sections[s] for s in tpl["sections"])
            if all_fields_done and all_sections_done:
                new_status = "completed"
        elif user_tpl_now:
            def _is_filled(f, v):
                if f.get("type") == "image":
                    return isinstance(v, dict) and v.get("__image__")
                if f.get("type") == "table":
                    return isinstance(v, list) and len(v) > 0
                return v not in (None, "")
            all_filled = all(_is_filled(f, new_fields.get(f["key"])) for f in user_tpl_now.get("fields", []))
            if all_filled:
                new_status = "completed"

        await db.chats.update_one(
            {"chat_id": chat_id},
            {"$set": {"fields": new_fields, "sections": new_sections, "status": new_status}},
        )

        updated_chat = await db.chats.find_one({"chat_id": chat_id}, {"_id": 0})

        done_payload = {
            "type": "done",
            "assistant_message": assistant_msg,
            "chat": updated_chat,
            "wallet_balance": new_balance,
            "cost_charged": cost,
            "low_balance_warning": new_balance < 10.0,
        }
        yield f"data: {json.dumps(done_payload, default=str)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============================================================
# File Uploads
# ============================================================

@api.post("/uploads")
async def upload_file(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    upload_id = f"up_{uuid.uuid4().hex[:12]}"
    safe_name = file.filename.replace("/", "_").replace("\\", "_")
    path = UPLOAD_DIR / f"{upload_id}_{safe_name}"
    content = await file.read()
    path.write_bytes(content)
    doc = {
        "upload_id": upload_id,
        "user_id": user.user_id,
        "filename": safe_name,
        "path": str(path),
        "size": len(content),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.uploads.insert_one(doc)
    doc.pop("_id", None)
    doc.pop("path", None)
    return doc


@api.post("/chats/{chat_id}/image")
async def chat_upload_image(
    chat_id: str,
    field_key: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Attach an image to a user-template image field in the given chat."""
    chat = await db.chats.find_one({"chat_id": chat_id, "user_id": user.user_id}, {"_id": 0})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    if not chat.get("user_template_id"):
        raise HTTPException(status_code=400, detail="Görsel yükleme yalnızca özel şablonlarda destekleniyor")
    ct = (file.content_type or "").lower()
    if not ct.startswith("image/"):
        raise HTTPException(status_code=400, detail="Yalnızca görsel dosyalar kabul edilir")

    upload_id = f"img_{uuid.uuid4().hex[:12]}"
    safe_name = file.filename.replace("/", "_").replace("\\", "_")
    path = UPLOAD_DIR / f"{upload_id}_{safe_name}"
    content = await file.read()
    path.write_bytes(content)

    # Validate the bytes are actually a decodable image (prevents render-time 500)
    try:
        from PIL import Image
        with Image.open(str(path)) as im:
            im.verify()
    except Exception:
        try:
            path.unlink()
        except Exception:
            pass
        raise HTTPException(status_code=400, detail="Geçerli bir görsel dosyası değil")

    preview_url = f"/api/uploads/file/{upload_id}"

    await db.uploads.insert_one({
        "upload_id": upload_id, "user_id": user.user_id, "filename": safe_name,
        "path": str(path), "size": len(content), "kind": "image",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    new_fields = dict(chat.get("fields", {}))
    prev = new_fields.get(field_key) or {}
    width_mm = prev.get("width_mm", 80) if isinstance(prev, dict) else 80
    new_fields[field_key] = {
        "__image__": True, "path": str(path), "preview_url": preview_url,
        "filename": safe_name, "width_mm": width_mm,
    }
    await db.chats.update_one({"chat_id": chat_id}, {"$set": {"fields": new_fields}})
    return {"success": True, "field_key": field_key, "preview_url": preview_url, "filename": safe_name, "width_mm": width_mm}


@api.patch("/chats/{chat_id}/image/{field_key}")
async def chat_update_image(chat_id: str, field_key: str, payload: Dict[str, Any], user: User = Depends(get_current_user)):
    """Update image metadata for a previously uploaded image field.

    Payload keys (all optional):
      - width_mm: number (20..170)
      - aspect_ratio: "16:9" | "4:3" | "1:1" | "3:4" | "original" — center-crop to that ratio
      - crop: {left, top, right, bottom} in pixel coords — explicit crop rectangle
    """
    chat = await db.chats.find_one({"chat_id": chat_id, "user_id": user.user_id}, {"_id": 0})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    fields = dict(chat.get("fields", {}))
    val = fields.get(field_key)
    if not (isinstance(val, dict) and val.get("__image__")):
        raise HTTPException(status_code=404, detail="Image field not found")

    updates: Dict[str, Any] = {}
    if "width_mm" in payload:
        try:
            w = float(payload["width_mm"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="width_mm must be a number")
        updates["width_mm"] = max(20.0, min(170.0, w))

    ar = payload.get("aspect_ratio")
    crop = payload.get("crop")
    if ar or crop:
        from PIL import Image
        try:
            im = Image.open(val["path"])
            im.load()
        except Exception:
            raise HTTPException(status_code=400, detail="Görsel açılamadı")

        if crop and isinstance(crop, dict):
            L = max(0, int(crop.get("left", 0)))
            T = max(0, int(crop.get("top", 0)))
            R = min(im.width, int(crop.get("right", im.width)))
            B = min(im.height, int(crop.get("bottom", im.height)))
            if R <= L or B <= T:
                raise HTTPException(status_code=400, detail="Geçersiz kırpma koordinatları")
            im = im.crop((L, T, R, B))
        elif ar and ar != "original":
            try:
                aw, ah = [float(x) for x in str(ar).split(":")]
                target = aw / ah
            except Exception:
                raise HTTPException(status_code=400, detail="Geçersiz aspect_ratio (16:9 gibi)")
            cur = im.width / im.height
            if cur > target:
                new_w = int(im.height * target)
                left = (im.width - new_w) // 2
                im = im.crop((left, 0, left + new_w, im.height))
            elif cur < target:
                new_h = int(im.width / target)
                top = (im.height - new_h) // 2
                im = im.crop((0, top, im.width, top + new_h))
        # Save cropped image, overwriting the original path
        try:
            fmt = "PNG" if val["path"].lower().endswith(".png") else "JPEG"
            if fmt == "JPEG" and im.mode in ("RGBA", "P"):
                im = im.convert("RGB")
            im.save(val["path"], fmt, quality=92)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Kaydedilemedi: {e}")
        # Bust cache: assign a new preview_url query param
        base = val.get("preview_url", "").split("?")[0]
        updates["preview_url"] = f"{base}?v={uuid.uuid4().hex[:6]}"
        updates["crop_applied"] = ar or "custom"
        updates["width_px"] = im.width
        updates["height_px"] = im.height

    if updates:
        val.update(updates)
        fields[field_key] = val
        await db.chats.update_one({"chat_id": chat_id}, {"$set": {"fields": fields}})
    return {"success": True, "field_key": field_key, **updates}


@api.patch("/chats/{chat_id}/table/{field_key}")
async def chat_update_table(chat_id: str, field_key: str, payload: Dict[str, Any], user: User = Depends(get_current_user)):
    """Replace the rows of a dynamic table field. Payload: {rows: [{col_key: value, ...}, ...]}."""
    chat = await db.chats.find_one({"chat_id": chat_id, "user_id": user.user_id}, {"_id": 0})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    ut = await _get_user_template(chat.get("user_template_id", "")) if chat.get("user_template_id") else None
    if not ut:
        raise HTTPException(status_code=400, detail="Tablo yalnızca özel şablonlarda destekleniyor")
    tpl_field = next((f for f in ut.get("fields", []) if f["key"] == field_key and f.get("type") == "table"), None)
    if not tpl_field:
        raise HTTPException(status_code=404, detail="Table field not found")
    col_keys = {c["key"] for c in tpl_field.get("columns", [])}
    rows_in = payload.get("rows") or []
    if not isinstance(rows_in, list):
        raise HTTPException(status_code=400, detail="rows must be a list")
    clean_rows: List[Dict[str, Any]] = []
    for r in rows_in:
        if not isinstance(r, dict):
            continue
        clean_rows.append({k: (v if v is not None else "") for k, v in r.items() if k in col_keys})
    new_fields = dict(chat.get("fields", {}))
    new_fields[field_key] = clean_rows
    await db.chats.update_one({"chat_id": chat_id}, {"$set": {"fields": new_fields}})
    return {"success": True, "field_key": field_key, "rows": clean_rows}


@api.get("/uploads/file/{upload_id}")
async def serve_upload(upload_id: str, user: User = Depends(get_current_user)):
    doc = await db.uploads.find_one({"upload_id": upload_id}, {"_id": 0})
    if not doc or doc.get("user_id") != user.user_id:
        raise HTTPException(status_code=404, detail="Not found")
    p = Path(doc["path"])
    if not p.exists():
        raise HTTPException(status_code=404, detail="File missing")
    return FileResponse(str(p), filename=doc.get("filename", p.name))


# ============================================================
# Report Generation & Download
# ============================================================

def _report_payload(chat: Dict[str, Any]) -> Dict[str, Any]:
    template = _template_by_id(chat.get("template_id", "")) if chat.get("template_id") else None
    labeled_fields = {}
    if template:
        for f in template["fields"]:
            labeled_fields[f["label"]] = chat.get("fields", {}).get(f["key"], "")
    return {
        "template_name": chat.get("template_name") or "Değerleme Raporu",
        "report_no": chat.get("report_no", "-"),
        "fields": labeled_fields,
        "sections": chat.get("sections", {}),
    }


@api.get("/chats/{chat_id}/download/{fmt}")
async def download_report(chat_id: str, fmt: str, user: User = Depends(get_current_user)):
    chat = await db.chats.find_one({"chat_id": chat_id, "user_id": user.user_id}, {"_id": 0})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # User template path: docxtpl-based rendering preserves original Word formatting
    if chat.get("user_template_id") and fmt == "docx":
        ut = await _get_user_template(chat["user_template_id"])
        if not ut or not _template_visible_to(ut, user):
            raise HTTPException(status_code=404, detail="Template not found")
        values = dict(chat.get("fields", {}))
        # Split out image fields + table lists
        image_paths: Dict[str, Any] = {}
        clean_values: Dict[str, Any] = {}
        for k, v in values.items():
            if isinstance(v, dict) and v.get("__image__") and v.get("path"):
                image_paths[k] = {"path": v["path"], "width_mm": v.get("width_mm", 80)}
            else:
                clean_values[k] = v  # lists (dynamic tables) pass through untouched — docxtpl loops them
        out_dir = REPORTS_DIR / chat_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"rapor_{chat['report_no'] or chat_id}.docx"
        render_docx(ut["prepared_docx_path"], str(out_path), clean_values, image_paths)
        return FileResponse(
            str(out_path),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=out_path.name,
        )
    if chat.get("user_template_id") and fmt == "pdf":
        raise HTTPException(status_code=400, detail="Özel şablonlar için şu an sadece DOCX indirilebilir")

    payload = _report_payload(chat)
    filename_base = f"rapor_{chat['report_no'] or chat_id}"
    if fmt == "pdf":
        out = REPORTS_DIR / f"{filename_base}.pdf"
        generate_pdf(payload, str(out))
        return FileResponse(str(out), media_type="application/pdf", filename=f"{filename_base}.pdf")
    if fmt == "docx":
        out = REPORTS_DIR / f"{filename_base}.docx"
        generate_docx(payload, str(out))
        return FileResponse(
            str(out),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"{filename_base}.docx",
        )
    raise HTTPException(status_code=400, detail="Format must be pdf or docx")


@api.post("/chats/{chat_id}/email")
async def email_report(chat_id: str, user: User = Depends(get_current_user)):
    """MOCK email dispatch — logs and returns success."""
    chat = await db.chats.find_one({"chat_id": chat_id, "user_id": user.user_id}, {"_id": 0})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    logger.info(f"[MOCK EMAIL] Report {chat['report_no']} sent to {user.email}")
    await db.email_logs.insert_one({
        "chat_id": chat_id,
        "user_id": user.user_id,
        "email": user.email,
        "report_no": chat.get("report_no"),
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "mock": True,
    })
    return {"success": True, "sent_to": user.email, "mock": True}


# ============================================================
# Analytics
# ============================================================

@api.get("/analytics/summary")
async def analytics_summary(
    user: User = Depends(get_current_user),
    days: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Return usage analytics for the given window.

    Query params:
      - days: 7 / 30 / 90 (preset window; default 30)
      - date_from / date_to: ISO date (YYYY-MM-DD); override `days` when both provided
    """
    now = datetime.now(timezone.utc)

    if date_from and date_to:
        try:
            since = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
            end_day = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc)
            until = end_day + timedelta(days=1)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_from / date_to")
    else:
        window_days = int(days) if days else 30
        if window_days not in (7, 30, 90) and (window_days < 1 or window_days > 365):
            raise HTTPException(status_code=400, detail="days must be 7, 30, 90 or 1..365")
        today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        since = today_start - timedelta(days=window_days - 1)
        until = today_start + timedelta(days=1)

    since_iso = since.isoformat()
    until_iso = until.isoformat()
    total_days = max(1, (until.date() - since.date()).days)

    since_iso = since.isoformat()
    until_iso = until.isoformat()
    total_days = max(1, (until.date() - since.date()).days)

    # Previous same-length window (for trend comparison)
    prev_since = since - timedelta(days=total_days)
    prev_until = since
    prev_since_iso = prev_since.isoformat()
    prev_until_iso = prev_until.isoformat()

    async def _load_window(s_iso: str, u_iso: str) -> tuple[list, list, list]:
        evs = await db.usage_events.find(
            {"user_id": user.user_id, "created_at": {"$gte": s_iso, "$lt": u_iso}},
            {"_id": 0},
        ).to_list(20000)
        cts = await db.chats.find(
            {"user_id": user.user_id, "created_at": {"$gte": s_iso, "$lt": u_iso}},
            {"_id": 0},
        ).to_list(20000)
        tps = await db.payment_transactions.find(
            {"user_id": user.user_id, "credited": True, "credited_at": {"$gte": s_iso, "$lt": u_iso}},
            {"_id": 0},
        ).to_list(2000)
        return evs, cts, tps

    events, chats_win, topups = await _load_window(since_iso, until_iso)
    prev_events, prev_chats, prev_topups = await _load_window(prev_since_iso, prev_until_iso)

    total_spent = round(sum(float(e.get("cost", 0)) for e in events), 2)
    total_messages = len(events)
    report_spend = round(sum(float(e.get("cost", 0)) for e in events if e.get("mode") == "report"), 2)

    # Chat & report stats
    reports_completed = sum(1 for c in chats_win if c.get("status") == "completed" and c.get("mode") == "report")
    reports_total = sum(1 for c in chats_win if c.get("mode") == "report")
    faq_count = sum(1 for c in chats_win if c.get("mode") == "faq")
    completion_rate = round((reports_completed / reports_total) * 100, 1) if reports_total else 0.0
    avg_spend_per_report = round(report_spend / reports_completed, 2) if reports_completed else 0.0
    total_topped_up = float(round(sum(float(t.get("credit_try", 0)) for t in topups), 2))

    # Previous-window stats
    prev_spent = round(sum(float(e.get("cost", 0)) for e in prev_events), 2)
    prev_messages = len(prev_events)
    prev_report_spend = round(sum(float(e.get("cost", 0)) for e in prev_events if e.get("mode") == "report"), 2)
    prev_reports_completed = sum(1 for c in prev_chats if c.get("status") == "completed" and c.get("mode") == "report")
    prev_reports_total = sum(1 for c in prev_chats if c.get("mode") == "report")
    prev_faq = sum(1 for c in prev_chats if c.get("mode") == "faq")
    prev_completion_rate = round((prev_reports_completed / prev_reports_total) * 100, 1) if prev_reports_total else 0.0
    prev_avg_spend_per_report = round(prev_report_spend / prev_reports_completed, 2) if prev_reports_completed else 0.0
    prev_topped_up = float(round(sum(float(t.get("credit_try", 0)) for t in prev_topups), 2))

    def _delta_pct(current: float, previous: float) -> Optional[float]:
        """% change vs previous window. Returns None if previous is 0 and current is 0."""
        if previous == 0 and current == 0:
            return None
        if previous == 0:
            return None  # can't compute % from zero baseline; UI shows 'yeni'
        return round(((current - previous) / previous) * 100, 1)

    trends = {
        "spent": {"current": total_spent, "previous": prev_spent, "delta_pct": _delta_pct(total_spent, prev_spent)},
        "messages": {"current": total_messages, "previous": prev_messages, "delta_pct": _delta_pct(total_messages, prev_messages)},
        "reports_completed": {"current": reports_completed, "previous": prev_reports_completed, "delta_pct": _delta_pct(reports_completed, prev_reports_completed)},
        "reports_total": {"current": reports_total, "previous": prev_reports_total, "delta_pct": _delta_pct(reports_total, prev_reports_total)},
        "faq_conversations": {"current": faq_count, "previous": prev_faq, "delta_pct": _delta_pct(faq_count, prev_faq)},
        "avg_spend_per_report": {"current": avg_spend_per_report, "previous": prev_avg_spend_per_report, "delta_pct": _delta_pct(avg_spend_per_report, prev_avg_spend_per_report)},
        "completion_rate_pct": {"current": completion_rate, "previous": prev_completion_rate, "delta_pct": _delta_pct(completion_rate, prev_completion_rate)},
        "topped_up": {"current": total_topped_up, "previous": prev_topped_up, "delta_pct": _delta_pct(total_topped_up, prev_topped_up)},
    }

    # Template breakdown
    template_map: Dict[str, Dict[str, Any]] = {}
    for e in events:
        tid = e.get("template_id") or "faq"
        tname = e.get("template_name") or ("FAQ Sohbeti" if tid == "faq" else "-")
        b = template_map.setdefault(tid, {"template_id": tid, "name": tname, "messages": 0, "spent": 0.0})
        b["messages"] += 1
        b["spent"] += float(e.get("cost", 0))
    for c in chats_win:
        tid = c.get("template_id") or ("faq" if c.get("mode") == "faq" else None)
        if not tid:
            continue
        b = template_map.setdefault(tid, {"template_id": tid, "name": c.get("template_name") or "FAQ Sohbeti",
                                          "messages": 0, "spent": 0.0})
        b.setdefault("reports_total", 0)
        b.setdefault("reports_completed", 0)
        if c.get("mode") == "report":
            b["reports_total"] = b.get("reports_total", 0) + 1
            if c.get("status") == "completed":
                b["reports_completed"] = b.get("reports_completed", 0) + 1
    template_breakdown = sorted(
        [
            {
                "template_id": v["template_id"],
                "name": v["name"],
                "messages": v.get("messages", 0),
                "spent": round(v.get("spent", 0.0), 2),
                "reports_total": v.get("reports_total", 0),
                "reports_completed": v.get("reports_completed", 0),
            }
            for v in template_map.values()
        ],
        key=lambda x: x["spent"], reverse=True,
    )

    preferred = None
    if template_breakdown:
        preferred_pick = max(
            template_breakdown,
            key=lambda x: (x["reports_completed"], x["messages"], x["spent"]),
        )
        preferred = {
            "template_id": preferred_pick["template_id"],
            "name": preferred_pick["name"],
            "reports_completed": preferred_pick["reports_completed"],
            "messages": preferred_pick["messages"],
            "spent": preferred_pick["spent"],
        }

    # Daily spend (fill zeros)
    daily: Dict[str, float] = {}
    for e in events:
        try:
            d = datetime.fromisoformat(e["created_at"]).date().isoformat()
        except Exception:
            continue
        daily[d] = round(daily.get(d, 0.0) + float(e.get("cost", 0)), 2)
    daily_series = []
    for i in range(total_days):
        d = (since + timedelta(days=i)).date().isoformat()
        daily_series.append({"date": d, "amount": round(daily.get(d, 0.0), 2)})

    # Top-ups already loaded above (also for previous window trends)
    return {
        "window_days": total_days,
        "date_from": since.date().isoformat(),
        "date_to": (until - timedelta(days=1)).date().isoformat(),
        "prev_date_from": prev_since.date().isoformat(),
        "prev_date_to": (prev_until - timedelta(days=1)).date().isoformat(),
        "wallet_balance": user.wallet_balance,
        "totals": {
            "spent": total_spent,
            "messages": total_messages,
            "reports_total": reports_total,
            "reports_completed": reports_completed,
            "faq_conversations": faq_count,
            "topped_up": total_topped_up,
        },
        "kpis": {
            "avg_spend_per_report": avg_spend_per_report,
            "completion_rate_pct": completion_rate,
        },
        "trends": trends,
        "preferred_template": preferred,
        "template_breakdown": template_breakdown,
        "daily_spend": daily_series,
    }


@api.get("/analytics/export.csv")
async def analytics_export(
    user: User = Depends(get_current_user),
    days: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Export raw usage events for the window as CSV."""
    summary = await analytics_summary(user=user, days=days, date_from=date_from, date_to=date_to)
    since_iso = f"{summary['date_from']}T00:00:00+00:00"
    until_iso = f"{summary['date_to']}T23:59:59+00:00"

    events = await db.usage_events.find(
        {"user_id": user.user_id, "created_at": {"$gte": since_iso, "$lt": until_iso}},
        {"_id": 0},
    ).sort("created_at", 1).to_list(50000)
    topups = await db.payment_transactions.find(
        {"user_id": user.user_id, "credited": True, "credited_at": {"$gte": since_iso, "$lt": until_iso}},
        {"_id": 0},
    ).sort("credited_at", 1).to_list(5000)

    import csv, io
    buf = io.StringIO()
    buf.write("\ufeff")  # BOM so Excel opens UTF-8 correctly
    w = csv.writer(buf, delimiter=",", quoting=csv.QUOTE_MINIMAL)

    w.writerow(["# Kullanım Analitiği CSV Raporu"])
    w.writerow(["# Kullanıcı", user.email])
    w.writerow(["# Dönem", summary["date_from"], summary["date_to"]])
    w.writerow(["# Oluşturma", datetime.now(timezone.utc).isoformat()])
    w.writerow([])

    w.writerow(["=== ÖZET ==="])
    w.writerow(["Metrik", "Değer"])
    w.writerow(["Toplam Harcama (TL)", summary["totals"]["spent"]])
    w.writerow(["Toplam Mesaj", summary["totals"]["messages"]])
    w.writerow(["Rapor (Toplam)", summary["totals"]["reports_total"]])
    w.writerow(["Rapor (Tamamlanan)", summary["totals"]["reports_completed"]])
    w.writerow(["FAQ Sohbeti", summary["totals"]["faq_conversations"]])
    w.writerow(["Yüklenen Bakiye (TL)", summary["totals"]["topped_up"]])
    w.writerow(["Tamamlama Oranı (%)", summary["kpis"]["completion_rate_pct"]])
    w.writerow(["Rapor Başı Ort. (TL)", summary["kpis"]["avg_spend_per_report"]])
    w.writerow([])

    w.writerow(["=== ŞABLON BAZINDA ==="])
    w.writerow(["Şablon", "Mesaj", "Rapor (Tamamlanan/Toplam)", "Harcama (TL)"])
    for t in summary["template_breakdown"]:
        w.writerow([t["name"], t["messages"], f"{t['reports_completed']}/{t['reports_total']}", t["spent"]])
    w.writerow([])

    w.writerow(["=== GÜNLÜK HARCAMA ==="])
    w.writerow(["Tarih", "Harcama (TL)"])
    for d in summary["daily_spend"]:
        w.writerow([d["date"], d["amount"]])
    w.writerow([])

    w.writerow(["=== MESAJ DETAYLARI ==="])
    w.writerow(["Tarih/Saat", "Mod", "Şablon", "Sohbet ID", "Ücret (TL)"])
    for e in events:
        w.writerow([
            e.get("created_at", ""),
            e.get("mode", ""),
            e.get("template_name") or ("FAQ" if e.get("mode") == "faq" else "-"),
            e.get("chat_id", ""),
            e.get("cost", 0),
        ])
    w.writerow([])

    if topups:
        w.writerow(["=== BAKİYE YÜKLEMELERİ ==="])
        w.writerow(["Tarih", "Paket", "Ödenen (TL)", "Bonus (TL)", "Toplam Kredi (TL)"])
        for t in topups:
            w.writerow([
                t.get("credited_at", ""),
                t.get("package_id", ""),
                t.get("amount_try", 0),
                t.get("bonus_try", 0),
                t.get("credit_try", 0),
            ])

    csv_data = buf.getvalue().encode("utf-8")
    filename = f"kullanim_{summary['date_from']}_{summary['date_to']}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ============================================================
# Wallet + Stripe (Flow B via emergentintegrations)
# ============================================================

def _stripe_checkout(host_url: str) -> StripeCheckout:
    webhook_url = f"{host_url.rstrip('/')}/api/webhook/stripe"
    return StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)


@api.get("/wallet/packages")
async def wallet_packages():
    return {"packages": WALLET_PACKAGES, "currency": "TRY"}


@api.get("/wallet/costs")
async def wallet_costs():
    """Publish per-message costs so UI can show them transparently."""
    return {
        "faq": 2.0,
        "templates": [
            {"id": t["id"], "name": t["name"], "cost_per_message": t["cost_per_message"], "avg_report_cost": t["avg_report_cost"]}
            for t in REPORT_TEMPLATES
        ],
    }


@api.post("/wallet/checkout")
async def wallet_checkout(payload: Dict[str, Any], request: Request, user: User = Depends(get_current_user)):
    package_id = payload.get("package_id")
    origin_url = payload.get("origin_url")
    if not package_id or not origin_url:
        raise HTTPException(status_code=400, detail="package_id and origin_url required")
    pkg = get_package(package_id)
    if not pkg:
        raise HTTPException(status_code=400, detail="Invalid package")

    total_credit_try = pkg["amount_try"] + pkg["bonus_try"]

    host_url = str(request.base_url)
    checkout = _stripe_checkout(host_url)
    req = CheckoutSessionRequest(
        amount=float(pkg["amount_try"]),
        currency="try",
        success_url=f"{origin_url.rstrip('/')}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin_url.rstrip('/')}/payment/cancel",
        metadata={
            "user_id": user.user_id,
            "package_id": package_id,
            "credit_try": str(total_credit_try),
            "amount_try": str(pkg["amount_try"]),
            "bonus_try": str(pkg["bonus_try"]),
        },
    )
    session = await checkout.create_checkout_session(req)

    await db.payment_transactions.insert_one({
        "session_id": session.session_id,
        "user_id": user.user_id,
        "package_id": package_id,
        "amount_try": pkg["amount_try"],
        "bonus_try": pkg["bonus_try"],
        "credit_try": total_credit_try,
        "currency": "try",
        "status": "initiated",
        "payment_status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })

    return {"checkout_url": session.url, "session_id": session.session_id}


async def _credit_wallet_if_paid(session_id: str, request: Request) -> Dict[str, Any]:
    """Idempotent: if paid and not yet credited, add credit_try to user's wallet."""
    tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not tx:
        return {"found": False}
    if tx.get("payment_status") == "paid" and tx.get("credited"):
        return {"found": True, "already": True, "tx": tx}

    # Ask Stripe directly (fallback for delayed webhooks)
    host_url = str(request.base_url)
    checkout = _stripe_checkout(host_url)
    try:
        status: CheckoutStatusResponse = await checkout.get_checkout_status(session_id)
    except Exception as e:
        logger.warning(f"Stripe status fetch failed: {e}")
        return {"found": True, "tx": tx}

    is_paid = str(status.payment_status).lower() == "paid" or str(status.status).lower() == "complete"

    updates: Dict[str, Any] = {
        "status": status.status,
        "payment_status": status.payment_status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if is_paid and not tx.get("credited"):
        # atomic: only credit once
        result = await db.payment_transactions.update_one(
            {"session_id": session_id, "credited": {"$ne": True}},
            {"$set": {**updates, "credited": True, "credited_at": datetime.now(timezone.utc).isoformat()}},
        )
        if result.modified_count == 1:
            await db.users.update_one(
                {"user_id": tx["user_id"]},
                {"$inc": {"wallet_balance": float(tx["credit_try"])}},
            )
    else:
        await db.payment_transactions.update_one({"session_id": session_id}, {"$set": updates})

    tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    return {"found": True, "tx": tx, "paid": is_paid}


@api.get("/wallet/status/{session_id}")
async def wallet_status(session_id: str, request: Request):
    """Unauthenticated status endpoint (per playbook), returns limited fields."""
    result = await _credit_wallet_if_paid(session_id, request)
    if not result["found"]:
        raise HTTPException(status_code=404, detail="Transaction not found")
    tx = result["tx"]
    return {
        "session_id": tx["session_id"],
        "status": tx.get("status"),
        "payment_status": tx.get("payment_status"),
        "amount_try": tx.get("amount_try"),
        "credit_try": tx.get("credit_try"),
        "credited": tx.get("credited", False),
    }


@api.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    body = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    host_url = str(request.base_url)
    checkout = _stripe_checkout(host_url)
    try:
        result = await checkout.handle_webhook(body, sig)
    except Exception as e:
        logger.warning(f"Stripe webhook signature verification failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    session_id = getattr(result, "session_id", None)
    if session_id:
        # Reuse the paid+credit logic
        await _credit_wallet_if_paid(session_id, request)
    return {"received": True}


# ============================================================
# Mount & CORS
# ============================================================

app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
