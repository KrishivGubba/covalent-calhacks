"""
Shared DynamoDB budget row helpers: human-readable identity fields from JWT claims.

Used by ai-gateway and perplexity-gateway. Attribute names avoid DynamoDB reserved words
(e.g. display_name instead of name).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

# Avoid oversized DynamoDB items / console clutter
_MAX_STRING_LEN = 2048


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connection_provider_from_sub(sub: str) -> Optional[str]:
    """Auth0-style subject prefix, e.g. google-oauth2|123 -> google-oauth2."""
    if "|" in sub:
        return sub.split("|", 1)[0]
    return None


def _truncate(s: str) -> str:
    return s[:_MAX_STRING_LEN] if len(s) > _MAX_STRING_LEN else s


def _build_identity_update_expression(
    user_id: str,
    jwt_payload: Dict[str, Any],
    default_budget_limit: float,
) -> Tuple[str, Dict[str, str], Dict[str, Any]]:
    """Build UpdateExpression SET clauses for identity + budget row defaults."""
    ts = _utc_iso()
    eav: Dict[str, Any] = {
        ":ts": ts,
        ":zero": Decimal("0"),
        ":def_budget": Decimal(str(default_budget_limit)),
    }
    sets = [
        "last_seen_at = :ts",
        "profile_updated_at = :ts",
        "total_spend = if_not_exists(total_spend, :zero)",
        "budget_limit = if_not_exists(budget_limit, :def_budget)",
    ]
    ean: Dict[str, str] = {}

    prov = connection_provider_from_sub(user_id)
    if prov:
        sets.append("connection_provider = :conn_prov")
        eav[":conn_prov"] = prov

    # Map OIDC / Auth0-style claims to DynamoDB attributes
    claim_to_attr = [
        ("name", "display_name", ":disp_name"),
        ("email", "email", ":email"),
        ("picture", "picture", ":picture"),
        ("nickname", "nickname", ":nickname"),
        ("given_name", "given_name", ":given_name"),
        ("family_name", "family_name", ":family_name"),
        ("preferred_username", "preferred_username", ":pref_user"),
    ]
    for claim, attr, placeholder in claim_to_attr:
        val = jwt_payload.get(claim)
        if isinstance(val, str) and val.strip():
            sets.append(f"{attr} = {placeholder}")
            eav[placeholder] = _truncate(val.strip())

    if "email_verified" in jwt_payload:
        sets.append("email_verified = :email_verified")
        eav[":email_verified"] = bool(jwt_payload["email_verified"])

    return "SET " + ", ".join(sets), ean, eav


def sync_budget_user_row(
    table: Any,
    user_id: str,
    jwt_payload: Dict[str, Any],
    default_budget_limit: float,
) -> Dict[str, Any]:
    """
    Upsert last_seen / profile fields and ensure total_spend + budget_limit exist.
    Returns {"total_spend", "budget_limit"} from the updated item.
    """
    expr, ean, eav = _build_identity_update_expression(
        user_id, jwt_payload, default_budget_limit
    )
    kwargs: Dict[str, Any] = {
        "Key": {"user_id": user_id},
        "UpdateExpression": expr,
        "ExpressionAttributeValues": eav,
        "ReturnValues": "ALL_NEW",
    }
    if ean:
        kwargs["ExpressionAttributeNames"] = ean

    resp = table.update_item(**kwargs)
    item = resp.get("Attributes") or {}
    return {
        "total_spend": float(item.get("total_spend", 0)),
        "budget_limit": float(item.get("budget_limit", default_budget_limit)),
    }


def get_or_create_budget_row_minimal(
    table: Any,
    user_id: str,
    default_budget_limit: float,
) -> Dict[str, Any]:
    """Read-only path for anonymous users: no JWT profile fields."""
    resp = table.get_item(Key={"user_id": user_id})
    item = resp.get("Item")
    if item:
        return {
            "total_spend": float(item.get("total_spend", 0)),
            "budget_limit": float(item.get("budget_limit", default_budget_limit)),
        }
    table.put_item(
        Item={
            "user_id": user_id,
            "total_spend": 0,
            "budget_limit": default_budget_limit,
        }
    )
    return {"total_spend": 0.0, "budget_limit": default_budget_limit}
