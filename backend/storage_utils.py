"""Emergent Object Storage wrapper for KırCan Report AI.

Persistent object storage for user uploads, template files, and knowledge base docs.
Storage key is minted once at startup and reused for the whole process.
"""
import os
import uuid
import logging
import asyncio
from typing import Optional, Tuple
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
APP_NAME = "kircan-report-ai"

_storage_key: Optional[str] = None


def init_storage(force: bool = False) -> Optional[str]:
    """Mint (or reuse) a storage key. Returns None on failure — caller can fall back to local disk."""
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    if not EMERGENT_KEY:
        logger.warning("EMERGENT_LLM_KEY not set — object storage disabled")
        return None
    try:
        r = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
        r.raise_for_status()
        _storage_key = r.json()["storage_key"]
        logger.info("Object Storage initialized")
        return _storage_key
    except Exception as e:
        logger.exception(f"Object Storage init failed: {e}")
        _storage_key = None
        return None


def storage_available() -> bool:
    return _storage_key is not None or init_storage() is not None


def _put_sync(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    if not key:
        raise RuntimeError("Object storage unavailable")
    r = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120,
    )
    if r.status_code == 404:
        # storage key may have expired — refresh once
        key = init_storage(force=True)
        r = requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type},
            data=data, timeout=120,
        )
    r.raise_for_status()
    return r.json()


def _get_sync(path: str) -> Tuple[bytes, str]:
    key = init_storage()
    if not key:
        raise RuntimeError("Object storage unavailable")
    r = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    if r.status_code == 404:
        key = init_storage(force=True)
        r = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    r.raise_for_status()
    return r.content, r.headers.get("Content-Type", "application/octet-stream")


async def put_object(path: str, data: bytes, content_type: str) -> dict:
    return await asyncio.to_thread(_put_sync, path, data, content_type)


async def get_object(path: str) -> Tuple[bytes, str]:
    return await asyncio.to_thread(_get_sync, path)


async def get_object_to_file(path: str, dest: Path) -> Path:
    """Download and write to a local file (needed by libs like docxtpl/mammoth that require file paths)."""
    data, _ct = await get_object(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest


def storage_path(kind: str, owner_id: str, ext: str) -> str:
    """Build a namespaced storage path.

    Examples:
      kircan-report-ai/uploads/user_abc/uuid.pdf
      kircan-report-ai/kb/company_xyz/uuid.pdf
      kircan-report-ai/templates/user_abc/uuid.docx
    """
    ext = ext.lstrip(".").lower() or "bin"
    return f"{APP_NAME}/{kind}/{owner_id}/{uuid.uuid4().hex}.{ext}"


MIME_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif",
    "webp": "image/webp", "tif": "image/tiff", "tiff": "image/tiff", "bmp": "image/bmp",
    "pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv", "txt": "text/plain", "md": "text/markdown",
    "json": "application/json", "udf": "application/octet-stream",
}


def content_type_for(filename: str, fallback: str = "application/octet-stream") -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return MIME_TYPES.get(ext, fallback)
