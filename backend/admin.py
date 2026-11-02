"""Admin console API: workspace overview, user management, audit log.

Browser sessions of users with ``role == "admin"`` only (an API key cannot
reach these routes). Every change an admin makes is written to
``audit_log`` and shown in the console's Activity tab.

    GET    /api/admin/overview                     -> KPIs, 14-day activity, plans, health
    GET    /api/admin/users?q=                     -> users with usage and last activity
    POST   /api/admin/users                        -> create a user
    PATCH  /api/admin/users/{username}             -> role, plan, display name, disabled
    POST   /api/admin/users/{username}/password    -> set a new password (signs them out)
    POST   /api/admin/users/{username}/sessions/revoke -> sign them out everywhere
    GET    /api/admin/audit                        -> recent admin actions

Feedback analytics stay at ``GET /api/feedback/summary`` (also admin only).

Safety rules: an admin cannot demote or disable themselves, and the last
active admin cannot be demoted or disabled, so the workspace always keeps
someone who can manage it.
"""

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from backend.account import PLANS, USAGE_DAYS, usage
from backend.artifacts import artifacts
from backend.auth import (
    USERNAME_PATTERN,
    api_keys,
    create_user,
    hash_password,
    require_session_user,
    sessions,
    users,
)
from backend.config import settings
from backend.db import db, ping
from backend.feedback import feedback
from backend.observability import metrics_snapshot
from backend.threads import threads

audit_log = db["audit_log"]

router = APIRouter(prefix="/api/admin", tags=["admin"])

ROLES = ("analyst", "admin")
AUDIT_LIMIT = 50


def require_admin(user=Depends(require_session_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Administrators only."})
    return user


def _iso(value):
    if not value:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _days():
    today = datetime.now(timezone.utc).date()
    return [(today - timedelta(days=offset)).isoformat() for offset in range(USAGE_DAYS - 1, -1, -1)]


def _audit(admin, action, target, details=None):
    audit_log.insert_one(
        {
            "at": datetime.now(timezone.utc),
            "actor": admin["username"],
            "action": action,
            "target": target,
            "details": details or {},
        }
    )


def _active_admins(exclude=None):
    query = {"role": "admin", "disabled": {"$ne": True}}
    if exclude:
        query["username"] = {"$ne": exclude}
    return users.count_documents(query)


def _bad(code, message, status=400):
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _counts_by_user(collection, match=None):
    pipeline = ([{"$match": match}] if match else []) + [{"$group": {"_id": "$username", "n": {"$sum": 1}}}]
    return {row["_id"]: row["n"] for row in collection.aggregate(pipeline)}


# --------------------------------------------------
# Overview
# --------------------------------------------------

@router.get("/overview")
def overview(admin=Depends(require_admin)):
    days = _days()
    today = days[-1]
    week = set(days[-7:])

    per_day = {day: {"day": day, "messages": 0, "tokens": 0, "cost_usd": 0.0, "active_users": 0} for day in days}
    active_today, active_week = set(), set()
    per_user = {}
    for doc in usage.find({"day": {"$in": days}}):
        row = per_day[doc["day"]]
        messages = doc.get("messages", 0)
        row["messages"] += messages
        row["tokens"] += doc.get("tokens", 0)
        row["cost_usd"] += doc.get("cost_usd", 0.0)
        if messages:
            row["active_users"] += 1
            per_user[doc["username"]] = per_user.get(doc["username"], 0) + messages
            if doc["day"] == today:
                active_today.add(doc["username"])
            if doc["day"] in week:
                active_week.add(doc["username"])
    series = [{**row, "cost_usd": round(row["cost_usd"], 6)} for row in per_day.values()]

    plan_counts = {plan_id: 0 for plan_id in PLANS}
    role_counts = {role: 0 for role in ROLES}
    names = {}
    total_users = disabled = 0
    for doc in users.find({}, {"username": 1, "display_name": 1, "plan": 1, "role": 1, "disabled": 1}):
        total_users += 1
        names[doc["username"]] = doc.get("display_name") or doc["username"]
        if doc.get("disabled"):
            disabled += 1
        role = doc.get("role", "analyst")
        role_counts[role] = role_counts.get(role, 0) + 1
        plan = doc.get("plan") or settings.default_plan
        plan_counts[plan if plan in plan_counts else "free"] += 1

    top_users = [
        {"username": username, "display_name": names.get(username, username), "messages": count}
        for username, count in sorted(per_user.items(), key=lambda item: item[1], reverse=True)[:6]
    ]

    artifact_types = {row["_id"]: row["n"] for row in artifacts.aggregate(
        [{"$group": {"_id": "$type", "n": {"$sum": 1}}}]
    )}
    ratings = {row["_id"]: row["n"] for row in feedback.aggregate(
        [{"$group": {"_id": "$rating", "n": {"$sum": 1}}}]
    )}
    up, down = ratings.get("up", 0), ratings.get("down", 0)

    try:
        mongodb_ok = ping()
    except Exception:  # noqa: BLE001
        mongodb_ok = False

    return {
        "kpis": {
            "users": total_users,
            "disabled_users": disabled,
            "admins": role_counts.get("admin", 0),
            "active_today": len(active_today),
            "active_7d": len(active_week),
            "questions_today": per_day[today]["messages"],
            "questions_14d": sum(row["messages"] for row in series),
            "tokens_14d": sum(row["tokens"] for row in series),
            "cost_14d_usd": round(sum(row["cost_usd"] for row in series), 4),
            "conversations": threads.estimated_document_count(),
            "artifacts": sum(artifact_types.values()),
            "satisfaction": round(up / (up + down), 3) if up + down else None,
            "ratings": up + down,
            "active_sessions": sessions.count_documents({}),
        },
        "days": series,
        "plans": [{"id": plan_id, "name": PLANS[plan_id]["name"], "users": n} for plan_id, n in plan_counts.items()],
        "roles": role_counts,
        "top_users": top_users,
        "artifact_types": artifact_types,
        "system": {
            "mongodb": mongodb_ok,
            "openrouter_configured": bool(settings.openrouter_api_key),
            "default_model": settings.openui_model,
            "jev_enabled": settings.jev_enabled,
            "graphiti_enabled": settings.graphiti_enabled,
            "langfuse_enabled": bool(settings.langfuse_public_key and settings.langfuse_secret_key),
            "signup_enabled": settings.allow_signup,
            "plan_limits_enforced": settings.plan_limits_enforced,
            "cookie_secure": settings.cookie_secure,
        },
        "live": metrics_snapshot(),
    }


# --------------------------------------------------
# Users
# --------------------------------------------------

def _public_user(doc, usage_14d, last_day, conversations, artifact_counts, key_counts, last_seen):
    username = doc["username"]
    seen = last_seen.get(username)
    day = last_day.get(username)
    last_active = _iso(seen) if seen else (f"{day}T00:00:00+00:00" if day else None)
    return {
        "username": username,
        "display_name": doc.get("display_name") or username,
        "role": doc.get("role", "analyst"),
        "plan": doc.get("plan") or settings.default_plan,
        "disabled": bool(doc.get("disabled")),
        "created_at": _iso(doc.get("created_at")),
        "last_active": last_active,
        "signed_in": bool(seen),
        "messages_14d": usage_14d.get(username, 0),
        "conversations": conversations.get(username, 0),
        "artifacts": artifact_counts.get(username, 0),
        "api_keys": key_counts.get(username, 0),
    }


@router.get("/users")
def list_users(q: str | None = None, admin=Depends(require_admin)):
    query = {}
    if q and q.strip():
        pattern = re.escape(q.strip()[:60])
        query = {"$or": [{"username": {"$regex": pattern, "$options": "i"}},
                         {"display_name": {"$regex": pattern, "$options": "i"}}]}
    docs = list(users.find(query, {"password_hash": 0}).sort("created_at", -1).limit(500))

    days = _days()
    usage_14d, last_day = {}, {}
    for row in usage.aggregate([
        {"$match": {"day": {"$in": days}, "messages": {"$gt": 0}}},
        {"$group": {"_id": "$username", "n": {"$sum": "$messages"}, "last": {"$max": "$day"}}},
    ]):
        usage_14d[row["_id"]] = row["n"]
        last_day[row["_id"]] = row["last"]
    last_seen = {row["_id"]: row["last"] for row in sessions.aggregate(
        [{"$group": {"_id": "$username", "last": {"$max": "$last_seen"}}}]
    )}

    conversations = _counts_by_user(threads)
    artifact_counts = _counts_by_user(artifacts)
    key_counts = _counts_by_user(api_keys, {"revoked_at": None})

    return {
        "users": [
            _public_user(doc, usage_14d, last_day, conversations, artifact_counts, key_counts, last_seen)
            for doc in docs
        ],
        "plans": [{"id": plan["id"], "name": plan["name"]} for plan in PLANS.values()],
        "roles": list(ROLES),
        "me": admin["username"],
    }


class NewUser(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(default="", max_length=80)
    role: str = "analyst"
    plan: str | None = None


@router.post("/users", status_code=201)
def add_user(payload: NewUser, admin=Depends(require_admin)):
    username = payload.username.strip().lower()
    if not re.fullmatch(USERNAME_PATTERN, username):
        raise _bad("invalid_username", "Usernames are 3–32 characters: letters, numbers, dots, dashes or underscores.", 422)
    if payload.role not in ROLES:
        raise _bad("invalid_role", "Unknown role.")
    if payload.plan and payload.plan not in PLANS:
        raise _bad("unknown_plan", "Unknown plan.")
    display_name = " ".join(payload.display_name.split()) or username
    try:
        create_user(username, payload.password, display_name=display_name, role=payload.role)
    except DuplicateKeyError:
        raise _bad("username_taken", "That username is already taken.", 409) from None
    if payload.plan:
        users.update_one({"username": username}, {"$set": {"plan": payload.plan}})
    _audit(admin, "user.create", username, {"role": payload.role, "plan": payload.plan or settings.default_plan})
    return {"username": username}


class UserPatch(BaseModel):
    role: str | None = None
    plan: str | None = None
    display_name: str | None = Field(default=None, max_length=80)
    disabled: bool | None = None


def _target(username):
    doc = users.find_one({"username": username})
    if not doc:
        raise _bad("not_found", "User not found.", 404)
    return doc


@router.patch("/users/{username}")
def update_user(username: str, payload: UserPatch, admin=Depends(require_admin)):
    doc = _target(username)
    is_self = username == admin["username"]
    update, changes = {}, {}

    if payload.role is not None and payload.role != doc.get("role", "analyst"):
        if payload.role not in ROLES:
            raise _bad("invalid_role", "Unknown role.")
        if is_self:
            raise _bad("self_change", "You can't change your own role.")
        if doc.get("role") == "admin" and not doc.get("disabled") and _active_admins(exclude=username) == 0:
            raise _bad("last_admin", "The workspace needs at least one active administrator.")
        update["role"] = changes["role"] = payload.role

    if payload.plan is not None and payload.plan != (doc.get("plan") or settings.default_plan):
        if payload.plan not in PLANS:
            raise _bad("unknown_plan", "Unknown plan.")
        update["plan"] = changes["plan"] = payload.plan

    if payload.display_name is not None:
        name = " ".join(payload.display_name.split())
        if name and name != doc.get("display_name"):
            update["display_name"] = changes["display_name"] = name

    if payload.disabled is not None and payload.disabled != bool(doc.get("disabled")):
        if payload.disabled:
            if is_self:
                raise _bad("self_change", "You can't disable your own account.")
            if doc.get("role") == "admin" and _active_admins(exclude=username) == 0:
                raise _bad("last_admin", "The workspace needs at least one active administrator.")
        update["disabled"] = changes["disabled"] = payload.disabled

    if update:
        users.update_one({"username": username}, {"$set": update})
        if update.get("disabled"):
            # Disabled accounts are signed out everywhere immediately.
            sessions.delete_many({"username": username})
        _audit(admin, "user.update", username, changes)
        doc.update(update)

    return {
        "username": username,
        "display_name": doc.get("display_name") or username,
        "role": doc.get("role", "analyst"),
        "plan": doc.get("plan") or settings.default_plan,
        "disabled": bool(doc.get("disabled")),
    }


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=200)


@router.post("/users/{username}/password")
def reset_password(username: str, payload: PasswordReset, admin=Depends(require_admin)):
    _target(username)
    users.update_one({"username": username}, {"$set": {"password_hash": hash_password(payload.new_password)}})
    revoked = sessions.delete_many({"username": username}).deleted_count
    _audit(admin, "user.password_reset", username, {"sessions_revoked": revoked})
    return {"ok": True, "sessions_revoked": revoked}


@router.post("/users/{username}/sessions/revoke")
def revoke_sessions(username: str, admin=Depends(require_admin)):
    _target(username)
    if username == admin["username"]:
        raise _bad("self_change", "Use Settings → Account to sign out your other devices.")
    revoked = sessions.delete_many({"username": username}).deleted_count
    _audit(admin, "user.sessions_revoke", username, {"sessions_revoked": revoked})
    return {"ok": True, "sessions_revoked": revoked}


# --------------------------------------------------
# Audit log
# --------------------------------------------------

@router.get("/audit")
def audit(admin=Depends(require_admin)):
    return {
        "events": [
            {
                "at": _iso(doc["at"]),
                "actor": doc.get("actor"),
                "action": doc.get("action"),
                "target": doc.get("target"),
                "details": doc.get("details") or {},
            }
            for doc in audit_log.find({}).sort("at", -1).limit(AUDIT_LIMIT)
        ]
    }
