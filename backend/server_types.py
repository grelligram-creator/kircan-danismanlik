"""Shared type definitions."""
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional


class UserWithRole(BaseModel):
    user_id: str
    email: str
    name: str
    picture: str = ""
    wallet_balance: float = 0.0
    role: str = "user"  # 'super_admin' | 'admin' | 'user'
    company_id: Optional[str] = None
    blocked: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
