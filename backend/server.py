"""Main FastAPI backend for Real Estate Valuation AI Chat."""
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, UploadFile, File, Form, Cookie, Header, Depends
from fastapi.responses import FileResponse, JSONResponse
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
import httpx

from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType

from templates_data import REPORT_TEMPLATES, FAQ_ITEMS
from document_utils import parse_uploaded_file, generate_pdf, generate_docx

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

UPLOAD_DIR = ROOT_DIR / "uploads"
REPORTS_DIR = ROOT_DIR / "generated_reports"
UPLOAD_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')

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
    credits: int = 100
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

    # normalize created_at
    if isinstance(user_doc.get("created_at"), str):
        user_doc["created_at"] = datetime.fromisoformat(user_doc["created_at"])
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
            "credits": 100,
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


@api.post("/chats/{chat_id}/message")
async def send_message(
    chat_id: str,
    payload: Dict[str, Any],
    user: User = Depends(get_current_user),
):
    chat = await db.chats.find_one({"chat_id": chat_id, "user_id": user.user_id}, {"_id": 0})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Cost: FAQ=5, Report=10 credits per message
    cost = 5 if chat["mode"] == "faq" else 10
    if user.credits < cost:
        raise HTTPException(status_code=402, detail={"error": "insufficient_credits", "required": cost, "balance": user.credits})

    user_text = payload.get("content", "").strip()
    attachment_ids: List[str] = payload.get("attachment_ids", [])

    # Save user message
    user_msg = {
        "message_id": f"msg_{uuid.uuid4().hex[:10]}",
        "chat_id": chat_id,
        "role": "user",
        "content": user_text,
        "attachments": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Load prior history for context (last 20)
    history = await db.messages.find({"chat_id": chat_id}, {"_id": 0}).sort("created_at", 1).to_list(500)

    # Gather attachment content
    attachment_texts = []
    for aid in attachment_ids:
        att = await db.uploads.find_one({"upload_id": aid, "user_id": user.user_id}, {"_id": 0})
        if att:
            content = parse_uploaded_file(att["path"])
            attachment_texts.append(f"[Yüklenen dosya: {att['filename']}]\n{content[:8000]}")
            user_msg["attachments"].append({"upload_id": aid, "filename": att["filename"]})

    await db.messages.insert_one(user_msg)
    user_msg.pop("_id", None)

    # Build LLM chat
    system_prompt = _build_system_prompt(chat)
    llm = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=chat_id,
        system_message=system_prompt,
    ).with_model("anthropic", "claude-sonnet-5")

    # Inject history as context (except last user msg — we send fresh)
    # emergentintegrations LlmChat auto-tracks per session_id; we build a single message with history embedded.
    context_lines: List[str] = []
    for m in history[-20:]:
        if m["role"] == "user":
            context_lines.append(f"Kullanıcı: {m['content']}")
        elif m["role"] == "assistant":
            clean, _ = _extract_update(m["content"])
            context_lines.append(f"Asistan: {clean}")
    context_str = "\n\n".join(context_lines)

    full_prompt = user_text
    if attachment_texts:
        full_prompt = full_prompt + "\n\n" + "\n\n".join(attachment_texts)
    if context_str:
        full_prompt = f"[Önceki konuşma]\n{context_str}\n\n[Yeni mesaj]\n{full_prompt}"

    try:
        assistant_raw = await llm.send_message(UserMessage(text=full_prompt))
        if hasattr(assistant_raw, "content"):
            assistant_text = assistant_raw.content
        else:
            assistant_text = str(assistant_raw)
    except Exception as e:
        logger.exception("LLM error")
        raise HTTPException(status_code=500, detail=f"LLM hatası: {e}")

    clean_text, update = _extract_update(assistant_text)

    # Persist assistant message (clean text)
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

    # Apply updates to chat doc
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

    # Auto-complete: if all fields collected and all sections generated
    template = _template_by_id(chat.get("template_id", "")) if chat.get("template_id") else None
    if template:
        all_fields_done = all(k in new_fields and new_fields[k] not in (None, "") for k in [f["key"] for f in template["fields"]])
        all_sections_done = all(s in new_sections and new_sections[s] for s in template["sections"])
        if all_fields_done and all_sections_done:
            new_status = "completed"

    await db.chats.update_one(
        {"chat_id": chat_id},
        {"$set": {"fields": new_fields, "sections": new_sections, "status": new_status}},
    )

    # Deduct credits
    new_credits = max(0, user.credits - cost)
    await db.users.update_one({"user_id": user.user_id}, {"$set": {"credits": new_credits}})

    updated_chat = await db.chats.find_one({"chat_id": chat_id}, {"_id": 0})

    return {
        "user_message": user_msg,
        "assistant_message": assistant_msg,
        "chat": updated_chat,
        "credits": new_credits,
        "credit_cost": cost,
        "low_credit_warning": new_credits < 20,
    }


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
# Credits
# ============================================================

@api.get("/credits/packages")
async def credit_packages():
    return {"packages": [
        {"id": "starter", "name": "Başlangıç", "credits": 500, "price_try": 299, "popular": False},
        {"id": "pro", "name": "Profesyonel", "credits": 1500, "price_try": 799, "popular": True},
        {"id": "enterprise", "name": "Kurumsal", "credits": 5000, "price_try": 2499, "popular": False},
    ]}


@api.post("/credits/purchase")
async def purchase_credits(payload: Dict[str, str], user: User = Depends(get_current_user)):
    """MOCK credit purchase — adds credits directly."""
    pkg_id = payload.get("package_id")
    packages = {"starter": 500, "pro": 1500, "enterprise": 5000}
    if pkg_id not in packages:
        raise HTTPException(status_code=400, detail="Invalid package")
    added = packages[pkg_id]
    new_credits = user.credits + added
    await db.users.update_one({"user_id": user.user_id}, {"$set": {"credits": new_credits}})
    return {"success": True, "added": added, "credits": new_credits, "mock": True}


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
