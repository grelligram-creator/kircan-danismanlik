"""Admin & Super Admin endpoints for KırCan Report AI."""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Request
from fastapi.responses import FileResponse
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from pathlib import Path
import uuid
import shutil

from auth_deps import is_super_admin, is_admin_or_super, SUPER_ADMIN_EMAILS
from document_utils import parse_uploaded_file

admin_router = APIRouter(prefix="/api/admin")


def register_admin_routes(db, get_current_user, User):
    """Attach db + auth dep at import time (avoids circular imports)."""

    # ================================
    # Helpers
    # ================================
    async def _scope_users_query(user) -> Dict[str, Any]:
        """Super admin sees all; admin sees only their company."""
        if is_super_admin(user):
            return {}
        if user.role == "admin" and user.company_id:
            return {"company_id": user.company_id}
        raise HTTPException(status_code=403, detail="Yetkisiz")

    async def _get_target_user(user_id: str, actor) -> Dict[str, Any]:
        """Fetch a target user, enforcing scope."""
        doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
        if not is_super_admin(actor):
            if actor.role != "admin" or doc.get("company_id") != actor.company_id:
                raise HTTPException(status_code=403, detail="Bu kullanıcıyı yönetme yetkiniz yok")
        return doc

    # ================================
    # USER LIST / DETAIL
    # ================================
    @admin_router.get("/users")
    async def list_users(user: User = Depends(get_current_user)):
        if not is_admin_or_super(user):
            raise HTTPException(status_code=403, detail="Yetkisiz")
        q = await _scope_users_query(user)
        cursor = db.users.find(q, {"_id": 0}).sort("created_at", -1).limit(500)
        users_list = await cursor.to_list(500)
        # Enrich each with chat + spend summary
        for u in users_list:
            u.pop("credits", None)
            # Backfill defaults for legacy documents predating the RBAC change
            u.setdefault("role", "user")
            u.setdefault("company_id", None)
            u.setdefault("blocked", False)
            u.setdefault("wallet_balance", 0.0)
            uid = u["user_id"]
            u["chat_count"] = await db.chats.count_documents({"user_id": uid})
            events = await db.usage_events.find({"user_id": uid}, {"cost": 1}).to_list(20000)
            u["total_spent"] = round(sum(float(e.get("cost", 0)) for e in events), 2)
        # attach company names
        company_ids = list({u.get("company_id") for u in users_list if u.get("company_id")})
        companies = {}
        if company_ids:
            async for c in db.companies.find({"company_id": {"$in": company_ids}}, {"_id": 0}):
                companies[c["company_id"]] = c.get("name", "")
        for u in users_list:
            u["company_name"] = companies.get(u.get("company_id"), None)
        return {"users": users_list}

    @admin_router.get("/users/{user_id}")
    async def get_user_detail(user_id: str, user: User = Depends(get_current_user)):
        if not is_admin_or_super(user):
            raise HTTPException(status_code=403, detail="Yetkisiz")
        target = await _get_target_user(user_id, user)
        chats = await db.chats.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
        wallet_tx = await db.wallet_ledger.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
        return {"user": target, "chats": chats, "wallet_transactions": wallet_tx}

    @admin_router.get("/users/{user_id}/chat/{chat_id}")
    async def get_user_chat(user_id: str, chat_id: str, user: User = Depends(get_current_user)):
        if not is_admin_or_super(user):
            raise HTTPException(status_code=403, detail="Yetkisiz")
        await _get_target_user(user_id, user)
        chat = await db.chats.find_one({"chat_id": chat_id, "user_id": user_id}, {"_id": 0})
        if not chat:
            raise HTTPException(status_code=404, detail="Sohbet bulunamadı")
        msgs = await db.messages.find({"chat_id": chat_id}, {"_id": 0}).sort("created_at", 1).to_list(1000)
        return {"chat": chat, "messages": msgs}

    # ================================
    # WALLET MANAGEMENT
    # ================================
    @admin_router.post("/users/{user_id}/wallet/topup")
    async def topup_user_wallet(
        user_id: str,
        payload: Dict[str, Any],
        user: User = Depends(get_current_user),
    ):
        """Add TRY to a user's wallet. Admin uses their company budget; super admin uses free funds."""
        if not is_admin_or_super(user):
            raise HTTPException(status_code=403, detail="Yetkisiz")
        target = await _get_target_user(user_id, user)
        try:
            amount = float(payload.get("amount", 0))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Geçersiz tutar")
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Tutar sıfırdan büyük olmalı")
        note = str(payload.get("note", "")).strip()[:200]

        # Admin: deduct from own company budget
        if not is_super_admin(user):
            if not user.company_id:
                raise HTTPException(status_code=400, detail="Şirketiniz tanımlı değil")
            if target.get("company_id") != user.company_id:
                raise HTTPException(status_code=403, detail="Farklı şirket kullanıcısına aktarım yapılamaz")
            company = await db.companies.find_one({"company_id": user.company_id}, {"_id": 0})
            if not company:
                raise HTTPException(status_code=404, detail="Şirket bulunamadı")
            if float(company.get("budget_balance", 0)) < amount:
                raise HTTPException(status_code=400, detail="Şirket bütçesi yetersiz")
            await db.companies.update_one(
                {"company_id": user.company_id},
                {"$inc": {"budget_balance": -amount}},
            )

        await db.users.update_one({"user_id": user_id}, {"$inc": {"wallet_balance": amount}})
        await db.wallet_ledger.insert_one({
            "ledger_id": f"wl_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "amount": amount,
            "type": "admin_topup",
            "actor_user_id": user.user_id,
            "actor_email": user.email,
            "note": note,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        updated = await db.users.find_one({"user_id": user_id}, {"_id": 0})
        return {"success": True, "user": updated}

    # ================================
    # ROLE / BLOCK / DELETE (Super only)
    # ================================
    @admin_router.post("/users/{user_id}/role")
    async def set_user_role(user_id: str, payload: Dict[str, Any], user: User = Depends(get_current_user)):
        if not is_super_admin(user):
            raise HTTPException(status_code=403, detail="Sadece süper admin rol değiştirebilir")
        new_role = payload.get("role")
        if new_role not in ("user", "admin", "super_admin"):
            raise HTTPException(status_code=400, detail="Geçersiz rol")
        target = await _get_target_user(user_id, user)
        updates: Dict[str, Any] = {"role": new_role}
        # Attach or clear company for admins
        if new_role == "admin":
            company_id = payload.get("company_id")
            if company_id:
                updates["company_id"] = company_id
            elif not target.get("company_id"):
                # Auto-create a company for this admin if none provided
                new_company = {
                    "company_id": f"co_{uuid.uuid4().hex[:10]}",
                    "name": payload.get("company_name") or f"{target.get('name', 'Şirket')} A.Ş.",
                    "admin_user_id": user_id,
                    "budget_balance": 0.0,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                await db.companies.insert_one(new_company)
                updates["company_id"] = new_company["company_id"]
        await db.users.update_one({"user_id": user_id}, {"$set": updates})
        updated = await db.users.find_one({"user_id": user_id}, {"_id": 0})
        return {"success": True, "user": updated}

    @admin_router.post("/users/{user_id}/block")
    async def block_user(user_id: str, payload: Dict[str, Any], user: User = Depends(get_current_user)):
        if not is_super_admin(user):
            raise HTTPException(status_code=403, detail="Sadece süper admin engelleyebilir")
        blocked = bool(payload.get("blocked", True))
        await _get_target_user(user_id, user)
        await db.users.update_one({"user_id": user_id}, {"$set": {"blocked": blocked}})
        # Invalidate sessions on block
        if blocked:
            await db.user_sessions.delete_many({"user_id": user_id})
        return {"success": True, "blocked": blocked}

    @admin_router.delete("/users/{user_id}")
    async def delete_user(user_id: str, user: User = Depends(get_current_user)):
        if not is_super_admin(user):
            raise HTTPException(status_code=403, detail="Sadece süper admin silebilir")
        if user_id == user.user_id:
            raise HTTPException(status_code=400, detail="Kendinizi silemezsiniz")
        await _get_target_user(user_id, user)
        await db.users.delete_one({"user_id": user_id})
        await db.user_sessions.delete_many({"user_id": user_id})
        await db.chats.delete_many({"user_id": user_id})
        await db.messages.delete_many({"user_id": user_id})
        return {"success": True}

    # ================================
    # COMPANIES
    # ================================
    @admin_router.get("/companies")
    async def list_companies(user: User = Depends(get_current_user)):
        if not is_admin_or_super(user):
            raise HTTPException(status_code=403, detail="Yetkisiz")
        q = {} if is_super_admin(user) else {"company_id": user.company_id}
        companies = await db.companies.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
        for c in companies:
            c["user_count"] = await db.users.count_documents({"company_id": c["company_id"]})
        return {"companies": companies}

    @admin_router.post("/companies")
    async def create_company(payload: Dict[str, Any], user: User = Depends(get_current_user)):
        if not is_super_admin(user):
            raise HTTPException(status_code=403, detail="Sadece süper admin şirket oluşturabilir")
        name = str(payload.get("name", "")).strip()
        if not name:
            raise HTTPException(status_code=400, detail="Şirket adı gerekli")
        c = {
            "company_id": f"co_{uuid.uuid4().hex[:10]}",
            "name": name,
            "admin_user_id": payload.get("admin_user_id"),
            "budget_balance": 0.0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.companies.insert_one(c)
        if c.get("admin_user_id"):
            await db.users.update_one(
                {"user_id": c["admin_user_id"]},
                {"$set": {"company_id": c["company_id"], "role": "admin"}},
            )
        c.pop("_id", None)
        return {"company": c}

    @admin_router.post("/companies/{company_id}/budget/topup")
    async def topup_company_budget(company_id: str, payload: Dict[str, Any], user: User = Depends(get_current_user)):
        """Super admin manually adds funds to a company's budget."""
        if not is_super_admin(user):
            raise HTTPException(status_code=403, detail="Sadece süper admin bütçe ekleyebilir")
        try:
            amount = float(payload.get("amount", 0))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Geçersiz tutar")
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Tutar sıfırdan büyük olmalı")
        c = await db.companies.find_one({"company_id": company_id}, {"_id": 0})
        if not c:
            raise HTTPException(status_code=404, detail="Şirket bulunamadı")
        await db.companies.update_one({"company_id": company_id}, {"$inc": {"budget_balance": amount}})
        await db.company_ledger.insert_one({
            "ledger_id": f"cl_{uuid.uuid4().hex[:12]}",
            "company_id": company_id,
            "amount": amount,
            "type": "super_admin_topup",
            "actor_user_id": user.user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        updated = await db.companies.find_one({"company_id": company_id}, {"_id": 0})
        return {"success": True, "company": updated}

    # ================================
    # INVITES
    # ================================
    @admin_router.post("/invites")
    async def create_invite(payload: Dict[str, Any], request: Request, user: User = Depends(get_current_user)):
        """Admin/super admin generates an invite code for a new user."""
        if not is_admin_or_super(user):
            raise HTTPException(status_code=403, detail="Yetkisiz")
        role = payload.get("role", "user")
        if role not in ("user", "admin"):
            raise HTTPException(status_code=400, detail="Geçersiz rol")
        if role == "admin" and not is_super_admin(user):
            raise HTTPException(status_code=403, detail="Admin davet etme yetkisi sadece süper adminde")
        # Determine target company
        company_id = payload.get("company_id")
        if is_super_admin(user):
            if role == "admin" and not company_id:
                # create company on-the-fly
                cname = payload.get("company_name") or "Yeni Şirket"
                nc = {
                    "company_id": f"co_{uuid.uuid4().hex[:10]}",
                    "name": cname, "admin_user_id": None, "budget_balance": 0.0,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                await db.companies.insert_one(nc)
                company_id = nc["company_id"]
            elif not company_id:
                company_id = None  # global user
        else:
            company_id = user.company_id
        email = str(payload.get("email", "")).strip().lower() or None
        code = f"inv_{uuid.uuid4().hex[:14]}"
        invite = {
            "invite_id": code,
            "code": code,
            "role": role,
            "company_id": company_id,
            "email": email,
            "used": False,
            "created_by": user.user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.company_invites.insert_one(invite)
        invite.pop("_id", None)

        # Always compute the canonical join URL (production if APP_BASE_URL set)
        import os as _os
        from urllib.parse import urlparse as _urlparse
        _canonical_base = str(_os.environ.get("APP_BASE_URL", "")).rstrip("/")
        if not _canonical_base:
            _canonical_base = str(payload.get("origin_url") or "").rstrip("/")
        if not _canonical_base:
            _canonical_base = (request.headers.get("origin") or "").rstrip("/")
        if not _canonical_base:
            _ref = request.headers.get("referer") or ""
            if _ref:
                _p = _urlparse(_ref)
                if _p.scheme and _p.netloc:
                    _canonical_base = f"{_p.scheme}://{_p.netloc}"
        canonical_join_url = f"{_canonical_base}/join/{code}" if _canonical_base else f"/join/{code}"

        # Optionally email the invite link via Resend
        email_sent = False
        email_error = None
        if email:
            try:
                from email_utils import send_email, invite_email
                join_url = canonical_join_url
                if not _canonical_base:
                    raise RuntimeError("Davet bağlantısı için origin belirlenemedi")
                company_name = None
                if company_id:
                    co = await db.companies.find_one({"company_id": company_id}, {"_id": 0, "name": 1})
                    company_name = co.get("name") if co else None
                html = invite_email(
                    inviter_email=user.email,
                    company_name=company_name,
                    role=role,
                    join_url=join_url,
                )
                await send_email(
                    to=email,
                    subject="KırCan Report AI · Davetiye",
                    html=html,
                )
                email_sent = True
            except Exception as e:
                import logging as _logging
                _logging.getLogger(__name__).exception("Invite email dispatch failed")
                raw = str(e)
                # Sanitize provider-specific noise for the client
                if "validation_error" in raw or "You can only send" in raw:
                    email_error = "Alıcı adres Resend hesabınızda doğrulanmamış. Test modu için doğrulanmış e-posta kullanın."
                elif "rate" in raw.lower():
                    email_error = "E-posta gönderim hız limiti aşıldı. Kısa süre sonra tekrar deneyin."
                else:
                    email_error = "E-posta gönderilemedi. Lütfen daha sonra tekrar deneyin."

        return {"invite": invite, "join_url": canonical_join_url, "email_sent": email_sent, "email_error": email_error}

    @admin_router.get("/invites")
    async def list_invites(request: Request, user: User = Depends(get_current_user)):
        if not is_admin_or_super(user):
            raise HTTPException(status_code=403, detail="Yetkisiz")
        q = {} if is_super_admin(user) else {"company_id": user.company_id}
        invites = await db.company_invites.find(q, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
        import os as _os
        base = str(_os.environ.get("APP_BASE_URL", "")).rstrip("/")
        if not base:
            base = (request.headers.get("origin") or "").rstrip("/")
        return {"invites": invites, "join_url_prefix": f"{base}/join" if base else "/join"}

    @admin_router.delete("/invites/{code}")
    async def revoke_invite(code: str, user: User = Depends(get_current_user)):
        if not is_admin_or_super(user):
            raise HTTPException(status_code=403, detail="Yetkisiz")
        inv = await db.company_invites.find_one({"code": code}, {"_id": 0})
        if not inv:
            raise HTTPException(status_code=404, detail="Davet bulunamadı")
        if not is_super_admin(user) and inv.get("company_id") != user.company_id:
            raise HTTPException(status_code=403, detail="Yetkisiz")
        await db.company_invites.delete_one({"code": code})
        return {"success": True}

    # ================================
    # SYSTEM ANALYTICS (Super Admin overview)
    # ================================
    @admin_router.get("/system/summary")
    async def system_summary(user: User = Depends(get_current_user)):
        if not is_admin_or_super(user):
            raise HTTPException(status_code=403, detail="Yetkisiz")
        q = await _scope_users_query(user)
        total_users = await db.users.count_documents(q)
        user_ids: List[str] = []
        async for u in db.users.find(q, {"user_id": 1, "_id": 0}):
            user_ids.append(u["user_id"])
        total_chats = await db.chats.count_documents({"user_id": {"$in": user_ids}}) if user_ids else 0
        events = await db.usage_events.find({"user_id": {"$in": user_ids}}, {"cost": 1}).to_list(50000) if user_ids else []
        total_spent = round(sum(float(e.get("cost", 0)) for e in events), 2)
        # Wallet totals
        wallet_total = 0.0
        async for u in db.users.find(q, {"wallet_balance": 1, "_id": 0}):
            wallet_total += float(u.get("wallet_balance", 0))
        wallet_total = round(wallet_total, 2)
        # Company budgets (super only)
        company_budgets = 0.0
        company_count = 0
        if is_super_admin(user):
            async for c in db.companies.find({}, {"budget_balance": 1, "_id": 0}):
                company_budgets += float(c.get("budget_balance", 0))
                company_count += 1
        return {
            "total_users": total_users,
            "total_chats": total_chats,
            "total_spent": total_spent,
            "wallet_balance_sum": wallet_total,
            "company_budget_sum": round(company_budgets, 2),
            "company_count": company_count,
        }

    return admin_router
