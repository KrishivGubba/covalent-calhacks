"""
Onboarding endpoints.
"""
import json
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..dependencies import get_encrypted_conn
from logger import get_logger

log = get_logger()
router = APIRouter()

ONBOARDING_PROFILE_CATEGORY = "onboarding_profile"
ONBOARDING_PROFILE_JSON_KEY = "onboarding_profile_json"
ONBOARDING_PROFILE_SUMMARY_KEY = "onboarding_profile_summary"


class OnboardingProfileRequest(BaseModel):
    name: str
    company_name: str
    role: str
    work_summary: str
    key_projects: list[str]
    source_of_truth: list[str]
    usage_scope: str


def _normalize_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a string")
    trimmed = value.strip()
    if not trimmed:
        raise HTTPException(status_code=400, detail=f"{field_name} is required")
    return trimmed


def _normalize_string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a list of strings")
    normalized: list[str] = []
    for item in value:
        if isinstance(item, str):
            trimmed = item.strip()
            if trimmed:
                normalized.append(trimmed)
    if not normalized:
        raise HTTPException(status_code=400, detail=f"{field_name} must contain at least one item")
    return normalized


def _get_root_node_uuid(create_if_missing: bool = False) -> Optional[str]:
    conn = get_encrypted_conn()
    try:
        cursor = conn.cursor()
        row = cursor.execute(
            "SELECT UUID FROM node_table WHERE parent_uuid IS NULL ORDER BY created ASC LIMIT 1"
        ).fetchone()
        if row:
            return row[0]

        if not create_if_missing:
            return None

        root_uuid = str(uuid.uuid4())
        now_iso = datetime.utcnow().isoformat()
        cursor.execute(
            """
            INSERT INTO node_table (UUID, Metadata, created, last_modified, parent_uuid, children_uuid_arr, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (root_uuid, "Root", now_iso, now_iso, None, "[]", None),
        )
        conn.commit()
        log.info(f"🌱 Created root node for onboarding profile: {root_uuid[:8]}...")
        return root_uuid
    finally:
        conn.close()


def _load_profile_from_db(root_uuid: str) -> Optional[dict]:
    conn = get_encrypted_conn()
    try:
        cursor = conn.cursor()
        rows = cursor.execute(
            """
            SELECT key, info
            FROM data_table
            WHERE Node_UUID = ? AND category = ?
            ORDER BY rowid DESC
            """,
            (root_uuid, ONBOARDING_PROFILE_CATEGORY),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return None

    for key, info in rows:
        if key == ONBOARDING_PROFILE_JSON_KEY:
            try:
                parsed = json.loads(info)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                log.warning("⚠️ Invalid onboarding JSON payload in data_table")
                return None

    return None


def _build_profile_summary(profile: dict) -> str:
    key_projects = ", ".join(profile.get("key_projects", []))
    sources = ", ".join(profile.get("source_of_truth", []))
    return (
        "Onboarding profile:\n"
        f"- Name: {profile.get('name')}\n"
        f"- Company: {profile.get('company_name')}\n"
        f"- Role: {profile.get('role')}\n"
        f"- Work summary: {profile.get('work_summary')}\n"
        f"- Key projects: {key_projects}\n"
        f"- Sources of truth: {sources}\n"
        f"- Usage scope: {profile.get('usage_scope')}\n"
    )


@router.get("/onboarding/profile")
async def get_onboarding_profile():
    """Return the saved onboarding profile, if it exists."""
    root_uuid = _get_root_node_uuid(create_if_missing=False)
    if not root_uuid:
        return {"profile": None}

    profile = _load_profile_from_db(root_uuid)
    return {"profile": profile}


@router.post("/onboarding/profile")
async def save_onboarding_profile(body: OnboardingProfileRequest):
    """
    Save onboarding profile in graph.db root node data.
    Replaces previous onboarding profile entries to keep writes idempotent.
    """
    profile = {
        "name": _normalize_non_empty_string(body.name, "name"),
        "company_name": _normalize_non_empty_string(body.company_name, "company_name"),
        "role": _normalize_non_empty_string(body.role, "role"),
        "work_summary": _normalize_non_empty_string(body.work_summary, "work_summary"),
        "key_projects": _normalize_string_list(body.key_projects, "key_projects"),
        "source_of_truth": _normalize_string_list(body.source_of_truth, "source_of_truth"),
        "usage_scope": _normalize_non_empty_string(body.usage_scope, "usage_scope"),
    }
    saved_at = datetime.utcnow().isoformat()
    profile["saved_at"] = saved_at

    root_uuid = _get_root_node_uuid(create_if_missing=True)
    if not root_uuid:
        raise HTTPException(status_code=500, detail="Failed to resolve root node")

    profile_json = json.dumps(profile, ensure_ascii=False)
    profile_summary = _build_profile_summary(profile)

    conn = get_encrypted_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM data_table WHERE Node_UUID = ? AND category = ?",
            (root_uuid, ONBOARDING_PROFILE_CATEGORY),
        )

        cursor.execute(
            """
            INSERT INTO data_table (UUID, Node_UUID, key, type, info, category)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), root_uuid, ONBOARDING_PROFILE_JSON_KEY, "json", profile_json, ONBOARDING_PROFILE_CATEGORY),
        )
        cursor.execute(
            """
            INSERT INTO data_table (UUID, Node_UUID, key, type, info, category)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), root_uuid, ONBOARDING_PROFILE_SUMMARY_KEY, "text", profile_summary, ONBOARDING_PROFILE_CATEGORY),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "profile": profile,
        "saved_at": saved_at,
        "root_node_uuid": root_uuid,
    }
