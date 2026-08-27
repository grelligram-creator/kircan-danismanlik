"""Knowledge base module for KırCan Report AI.

Admins/super-admins upload PDF/DOCX/TXT files.
Text is extracted and injected into Claude system prompt for both FAQ and report chats.
Scope:
  - global: uploaded by super_admin, visible to everyone
  - company: uploaded by admin, visible to users in their company (and super admins)
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import uuid

from auth_deps import is_super_admin, is_admin_or_super
from document_utils import parse_uploaded_file


kb_router = APIRouter(prefix="/api/kb")

KB_DIR = Path(__file__).parent / "knowledge_base_files"
KB_DIR.mkdir(exist_ok=True)

# Max extracted text per document injected as context (chars)
MAX_KB_TEXT_PER_DOC = 6000
MAX_KB_TOTAL_CHARS = 25000


def register_kb_routes(db, get_current_user, User):

    @kb_router.post("/upload")
    async def upload_kb_doc(
        file: UploadFile = File(...),
        scope: str = Form("company"),  # 'global' | 'company'
        title: str = Form(""),
        user: User = Depends(get_current_user),
    ):
        if not is_admin_or_super(user):
            raise HTTPException(status_code=403, detail="Sadece admin ve süper admin dosya yükleyebilir")
        if scope not in ("global", "company"):
            raise HTTPException(status_code=400, detail="Geçersiz kapsam")
        if scope == "global" and not is_super_admin(user):
            raise HTTPException(status_code=403, detail="Global doküman yalnızca süper admin tarafından eklenebilir")
        if scope == "company" and not user.company_id and not is_super_admin(user):
            raise HTTPException(status_code=400, detail="Şirketiniz tanımlı değil")

        allowed = (".pdf", ".docx", ".txt", ".md", ".csv", ".xlsx")
        if not file.filename or not file.filename.lower().endswith(allowed):
            raise HTTPException(status_code=400, detail="Desteklenen formatlar: PDF, DOCX, TXT, MD, CSV, XLSX")

        doc_id = f"kb_{uuid.uuid4().hex[:12]}"
        safe_name = file.filename.replace("/", "_").replace("\\", "_")
        content = await file.read()

        # Persist to Object Storage (with pod-local fallback only if storage is unavailable)
        storage_path_str = None
        try:
            from storage_utils import put_object, storage_path as make_storage_path, content_type_for
            ext = safe_name.rsplit(".", 1)[-1] if "." in safe_name else "bin"
            owner = user.company_id or "global"
            key = make_storage_path("kb", owner, ext)
            result = await put_object(key, content, content_type_for(safe_name))
            storage_path_str = result["path"]
        except Exception as e:
            import logging as _lg
            _lg.getLogger(__name__).warning(f"KB object storage upload failed, falling back to local: {e}")

        # Write to a temp file so parsers (docx/pdf/xlsx libs) can read it — cleaned up after parsing.
        import tempfile as _tempfile
        with _tempfile.NamedTemporaryFile(delete=False, suffix=f"_{safe_name}", dir=str(KB_DIR)) as _tf:
            _tf.write(content)
            tmp_local = Path(_tf.name)

        try:
            text = parse_uploaded_file(str(tmp_local))
        except Exception as e:
            if storage_path_str:
                tmp_local.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail=f"Dosya okunamadı: {e}")
        finally:
            # If we successfully stored to object storage, remove the local temp copy
            if storage_path_str:
                try:
                    tmp_local.unlink(missing_ok=True)
                except Exception:
                    pass

        record = {
            "doc_id": doc_id,
            "title": title.strip() or safe_name,
            "filename": safe_name,
            "storage_path": storage_path_str,
            "path": None if storage_path_str else str(tmp_local),
            "scope": scope,
            "company_id": None if scope == "global" else user.company_id,
            "uploaded_by": user.user_id,
            "uploader_email": user.email,
            "text_preview": text[:2000],
            "text_content": text[:20000],
            "size": len(content),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.kb_docs.insert_one(record)
        record.pop("_id", None)
        record.pop("text_content", None)
        return {"document": record}

    @kb_router.get("/list")
    async def list_kb_docs(user: User = Depends(get_current_user)):
        """List documents visible to the user based on their scope."""
        q = _visibility_query(user)
        cursor = db.kb_docs.find(q, {"_id": 0, "text_content": 0, "path": 0}).sort("created_at", -1)
        docs = await cursor.to_list(500)
        return {"documents": docs}

    @kb_router.delete("/{doc_id}")
    async def delete_kb_doc(doc_id: str, user: User = Depends(get_current_user)):
        d = await db.kb_docs.find_one({"doc_id": doc_id}, {"_id": 0})
        if not d:
            raise HTTPException(status_code=404, detail="Doküman bulunamadı")
        # Super admin can delete anything; admin only their company's
        if not is_super_admin(user):
            if not (user.role == "admin" and d.get("company_id") == user.company_id):
                raise HTTPException(status_code=403, detail="Yetkisiz")
        # Object Storage has no delete API — soft-delete only (mark record and remove from index)
        if d.get("path"):
            try:
                Path(d["path"]).unlink(missing_ok=True)
            except Exception:
                pass
        await db.kb_docs.delete_one({"doc_id": doc_id})
        return {"success": True}

    @kb_router.post("/faq")
    async def create_faq_item(payload: Dict[str, Any], user: User = Depends(get_current_user)):
        """Add a Q&A pair directly (no file). Admin/super only.

        Payload: {question, answer, scope: 'global'|'company'}
        """
        from auth_deps import is_admin_or_super
        if not is_admin_or_super(user):
            raise HTTPException(status_code=403, detail="Sadece admin ve süper admin FAQ ekleyebilir")
        q = str(payload.get("question", "")).strip()
        a = str(payload.get("answer", "")).strip()
        scope = payload.get("scope", "company")
        if not q or not a:
            raise HTTPException(status_code=400, detail="Soru ve cevap boş olamaz")
        if scope not in ("global", "company"):
            raise HTTPException(status_code=400, detail="Geçersiz kapsam")
        if scope == "global" and not is_super_admin(user):
            raise HTTPException(status_code=403, detail="Global FAQ yalnızca süper admin ekleyebilir")
        if scope == "company" and not user.company_id and not is_super_admin(user):
            raise HTTPException(status_code=400, detail="Şirketiniz tanımlı değil")

        doc_id = f"faq_{uuid.uuid4().hex[:12]}"
        text_content = f"SORU: {q}\n\nCEVAP: {a}"
        record = {
            "doc_id": doc_id,
            "title": q[:200],
            "filename": None,
            "storage_path": None,
            "path": None,
            "scope": scope,
            "kind": "faq",
            "question": q,
            "answer": a,
            "company_id": None if scope == "global" else user.company_id,
            "uploaded_by": user.user_id,
            "uploader_email": user.email,
            "text_preview": text_content[:500],
            "text_content": text_content,
            "size": len(text_content.encode("utf-8")),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.kb_docs.insert_one(record)
        record.pop("_id", None)
        record.pop("text_content", None)
        return {"item": record}

    return kb_router


def _visibility_query(user) -> Dict[str, Any]:
    """Query for KB docs visible to this user."""
    if is_super_admin(user):
        return {}
    scopes: List[Dict[str, Any]] = [{"scope": "global"}]
    if user.company_id:
        scopes.append({"scope": "company", "company_id": user.company_id})
    return {"$or": scopes}


async def get_kb_context(db, user) -> str:
    """Return concatenated KB text to inject into an LLM system prompt.

    Trims per-doc and total to keep prompt size reasonable.
    """
    q = _visibility_query(user)
    total = 0
    parts: List[str] = []
    async for d in db.kb_docs.find(q, {"title": 1, "filename": 1, "text_content": 1, "_id": 0}):
        text = (d.get("text_content") or "").strip()
        if not text:
            continue
        snippet = text[:MAX_KB_TEXT_PER_DOC]
        title = d.get("title") or d.get("filename") or "Doküman"
        block = f"### {title}\n{snippet}"
        if total + len(block) > MAX_KB_TOTAL_CHARS:
            break
        parts.append(block)
        total += len(block)
    if not parts:
        return ""
    return "\n\n---\n\n".join(parts)
