"""Main FastAPI backend for Real Estate Valuation AI Chat."""
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, UploadFile, File, Form, Cookie, Header, Depends
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime, timezone, timedelta
import os
import uuid
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
async def list_templates():
    return {"templates": REPORT_TEMPLATES}


@api.get("/faq")
async def list_faq():
    return {"items": FAQ_ITEMS}


# ============================================================
# Chat Sessions
# ============================================================

def _template_by_id(tid: str) -> Optional[Dict[str, Any]]:
    return next((t for t in REPORT_TEMPLATES if t["id"] == tid), None)


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
    template = _template_by_id(template_id) if template_id else None

    chat_id = f"chat_{uuid.uuid4().hex[:10]}"
    title = "FAQ Sohbeti" if mode == "faq" else (template["name"] if template else "Yeni Rapor")

    chat_doc = {
        "chat_id": chat_id,
        "user_id": user.user_id,
        "title": title,
        "mode": mode,
        "template_id": template_id,
        "template_name": template["name"] if template else None,
        "fields": {},
        "sections": {},
        "status": "in_progress",
        "report_no": f"VAL-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}" if mode == "report" else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.chats.insert_one(chat_doc)
    chat_doc.pop("_id", None)

    # Seed system + first assistant message
    if mode == "report" and template:
        greeting = (
            f"Merhaba! **{template['name']}** hazırlamanıza yardımcı olacağım. "
            f"Size gerekli bilgileri sırayla soracağım ve raporu adım adım dolduracağız.\n\n"
            f"Başlayalım — **{template['fields'][0]['label']}** bilgisini paylaşır mısınız?\n\n"
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

def _build_system_prompt(chat: Dict[str, Any]) -> str:
    if chat["mode"] == "faq":
        faq_text = "\n\n".join([f"S: {q['q']}\nC: {q['a']}" for q in FAQ_ITEMS])
        return (
            "Sen deneyimli, SPK lisanslı bir gayrimenkul değerleme uzmanısın. "
            "Türkçe, net ve teknik olarak doğru cevaplar ver. "
            "Aşağıdaki bilgi bankasından yararlanabilirsin ancak dışına da çıkabilirsin:\n\n"
            + faq_text
        )

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

    system_prompt = _build_system_prompt(chat)
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
        if tpl:
            all_fields_done = all(k in new_fields and new_fields[k] not in (None, "")
                                   for k in [f["key"] for f in tpl["fields"]])
            all_sections_done = all(s in new_sections and new_sections[s] for s in tpl["sections"])
            if all_fields_done and all_sections_done:
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

    # All usage events for user in the window
    events = await db.usage_events.find(
        {"user_id": user.user_id, "created_at": {"$gte": since_iso, "$lt": until_iso}},
        {"_id": 0},
    ).to_list(20000)

    total_spent = round(sum(float(e.get("cost", 0)) for e in events), 2)
    total_messages = len(events)
    report_spend = round(sum(float(e.get("cost", 0)) for e in events if e.get("mode") == "report"), 2)

    # Chat & report stats (window based on chats.created_at ISO string)
    chats_win = await db.chats.find(
        {"user_id": user.user_id, "created_at": {"$gte": since_iso, "$lt": until_iso}},
        {"_id": 0},
    ).to_list(20000)
    reports_completed = sum(1 for c in chats_win if c.get("status") == "completed" and c.get("mode") == "report")
    reports_total = sum(1 for c in chats_win if c.get("mode") == "report")
    faq_count = sum(1 for c in chats_win if c.get("mode") == "faq")
    completion_rate = round((reports_completed / reports_total) * 100, 1) if reports_total else 0.0
    avg_spend_per_report = round(report_spend / reports_completed, 2) if reports_completed else 0.0

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

    # Top-ups (Stripe wallet purchases) in the window
    topups = await db.payment_transactions.find(
        {"user_id": user.user_id, "credited": True, "credited_at": {"$gte": since_iso, "$lt": until_iso}},
        {"_id": 0},
    ).to_list(1000)
    total_topped_up = float(round(sum(float(t.get("credit_try", 0)) for t in topups), 2))

    return {
        "window_days": total_days,
        "date_from": since.date().isoformat(),
        "date_to": (until - timedelta(days=1)).date().isoformat(),
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
