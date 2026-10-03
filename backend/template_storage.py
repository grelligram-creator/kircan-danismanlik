"""Template file persistence — bridges Emergent Object Storage with docxtpl/mammoth.

docxtpl and mammoth require real local file paths, so we keep a disposable local
cache at TEMPLATES_DIR/<template_id>/ and lazily hydrate it from Object Storage.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


async def write_template_to_storage(template_id: str, user_id: str, kind: str, data: bytes) -> str:
    """Upload a template bytes object (original or prepared) to Object Storage.

    `kind` is one of 'original', 'prepared', or 'snapshot_<version_id>'.
    Returns the storage path (string) stored in the DB document.
    """
    from storage_utils import put_object, storage_path, content_type_for
    obj_path = storage_path(f"templates/{kind}", user_id, "docx")
    ct = content_type_for("x.docx")
    result = await put_object(obj_path, data, ct)
    return result["path"]


async def ensure_prepared_local(ut: Dict, templates_dir: Path) -> str:
    """Hydrate the prepared.docx into local cache, return its path."""
    tpl_dir = templates_dir / ut["template_id"]
    tpl_dir.mkdir(parents=True, exist_ok=True)
    sp = ut.get("prepared_storage_path")
    legacy = ut.get("prepared_docx_path")
    dest = tpl_dir / "prepared.docx"

    if sp:
        if not dest.exists() or dest.stat().st_size == 0:
            from storage_utils import get_object_to_file
            await get_object_to_file(sp, dest)
        return str(dest)
    # legacy local-only template
    if legacy and Path(legacy).exists():
        return legacy
    raise FileNotFoundError(f"Template {ut.get('template_id')} has no prepared docx (storage={sp!r}, legacy={legacy!r})")


async def ensure_original_local(ut: Dict, templates_dir: Path) -> str:
    """Hydrate the original.docx into local cache, return its path."""
    tpl_dir = templates_dir / ut["template_id"]
    tpl_dir.mkdir(parents=True, exist_ok=True)
    sp = ut.get("original_storage_path")
    legacy = ut.get("original_docx_path")
    dest = tpl_dir / "original.docx"

    if sp:
        if not dest.exists() or dest.stat().st_size == 0:
            from storage_utils import get_object_to_file
            await get_object_to_file(sp, dest)
        return str(dest)
    if legacy and Path(legacy).exists():
        return legacy
    raise FileNotFoundError(f"Template {ut.get('template_id')} has no original docx")


async def ensure_both_local(ut: Dict, templates_dir: Path) -> Tuple[str, str]:
    """Convenience: return (original_path, prepared_path) local-cached."""
    orig = await ensure_original_local(ut, templates_dir)
    prep = await ensure_prepared_local(ut, templates_dir)
    return orig, prep


async def migrate_legacy_templates(db, templates_dir: Path) -> int:
    """One-shot migration on startup: any template with legacy local paths but no
    storage paths — upload them to Object Storage, update DB. Returns count migrated.
    """
    from storage_utils import storage_available
    if not storage_available():
        logger.warning("Object Storage unavailable — skipping template migration")
        return 0

    migrated = 0
    async for ut in db.user_templates.find(
        {"$or": [{"prepared_storage_path": {"$exists": False}},
                 {"prepared_storage_path": None}]},
        {"_id": 0, "template_id": 1, "user_id": 1, "original_docx_path": 1, "prepared_docx_path": 1},
    ):
        tid = ut.get("template_id")
        uid = ut.get("user_id") or "unknown"
        updates: Dict[str, str] = {}
        try:
            orig = ut.get("original_docx_path")
            prep = ut.get("prepared_docx_path")
            if orig and Path(orig).exists():
                data = Path(orig).read_bytes()
                sp = await write_template_to_storage(tid, uid, "original", data)
                updates["original_storage_path"] = sp
            if prep and Path(prep).exists():
                data = Path(prep).read_bytes()
                sp = await write_template_to_storage(tid, uid, "prepared", data)
                updates["prepared_storage_path"] = sp
        except Exception as e:
            logger.warning(f"Failed to migrate template {tid}: {e}")
            continue
        if updates:
            await db.user_templates.update_one({"template_id": tid}, {"$set": updates})
            migrated += 1
            logger.info(f"Migrated template {tid} → Object Storage")
    return migrated
