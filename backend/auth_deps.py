"""Role-based access helpers for KırCan Report AI."""
from fastapi import HTTPException, Depends
from typing import Optional

from server_types import UserWithRole

# Whitelist — this email always becomes super_admin on first login.
SUPER_ADMIN_EMAILS = {"grelligram@gmail.com"}


def is_super_admin(user: UserWithRole) -> bool:
    return user.role == "super_admin" or user.email.lower() in SUPER_ADMIN_EMAILS


def is_admin_or_super(user: UserWithRole) -> bool:
    return user.role in ("super_admin", "admin") or user.email.lower() in SUPER_ADMIN_EMAILS


def require_super_admin(user: UserWithRole) -> UserWithRole:
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="Bu işlem için süper admin yetkisi gerekir")
    return user


def require_admin(user: UserWithRole) -> UserWithRole:
    if not is_admin_or_super(user):
        raise HTTPException(status_code=403, detail="Bu işlem için admin yetkisi gerekir")
    return user
