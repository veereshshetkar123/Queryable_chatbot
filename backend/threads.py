"""Per-user conversation storage for the OpenUI chat.

Implements the REST contract of ``restStorage`` from
``@openuidev/react-headless`` (identity message format):

    GET    /api/threads/get              -> {"threads": [...], "nextCursor"?}
    POST   /api/threads/create           -> Thread
    GET    /api/threads/get/{id}         -> Message[]
    PATCH  /api/threads/update/{id}      -> Thread
    DELETE /api/threads/delete/{id}

Every thread belongs to the signed-in user; another user's thread is
reported as not found.
"""

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.artifacts import delete_for_thread
from backend.auth import require_user
from backend.db import db

threads = db["chat_threads"]

router = APIRouter(prefix="/api/threads", tags=["threads"])

PAGE_SIZE = 30
MAX_MESSAGES = 400


def ensure_indexes():
    threads.create_index([("username", 1), ("updatedAt", -1)])


def _now_ms():
    return int(time.time() * 1000)


def _public(doc):
    return {"id": doc["_id"], "title": doc.get("title") or "New conversation", "createdAt": doc["createdAt"]}


def message_text(message):
    """Text of an AG-UI message whose content is a string or content parts."""

    content = (message or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "\n".join(parts)
    return ""


def get_owned(thread_id, username):
    doc = threads.find_one({"_id": thread_id, "username": username})
    if not doc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Conversation not found."})
    return doc


def save_messages(thread_id, username, messages, meta=None):
    """Store the thread's messages.

    ``meta`` maps an assistant message id to server-side facts about how it
    was produced (trace id, route, model). It is kept apart from ``messages``
    because the browser resends the message list on every turn.
    """

    update = {"messages": messages[-MAX_MESSAGES:], "updatedAt": _now_ms()}
    for message_id, info in (meta or {}).items():
        update[f"meta.{message_id}"] = info
    threads.update_one({"_id": thread_id, "username": username}, {"$set": update})


class CreateThread(BaseModel):
    messages: list = []


class UpdateThread(BaseModel):
    id: str | None = None
    title: str | None = None


@router.get("/get")
def list_threads(cursor: str | None = None, user=Depends(require_user)):
    query = {"username": user["username"]}
    if cursor:
        try:
            query["updatedAt"] = {"$lt": int(cursor)}
        except ValueError:
            raise HTTPException(status_code=400, detail={"code": "bad_cursor", "message": "Invalid cursor."})

    docs = list(
        threads.find(query, {"messages": 0}).sort("updatedAt", -1).limit(PAGE_SIZE + 1)
    )
    result = {"threads": [_public(doc) for doc in docs[:PAGE_SIZE]]}
    if len(docs) > PAGE_SIZE:
        result["nextCursor"] = str(docs[PAGE_SIZE - 1]["updatedAt"])
    return result


@router.post("/create")
def create_thread(payload: CreateThread, user=Depends(require_user)):
    first = payload.messages[0] if payload.messages else {}
    title = " ".join(message_text(first).split())[:60] or "New conversation"
    now = _now_ms()
    doc = {
        "_id": str(uuid.uuid4()),
        "username": user["username"],
        "title": title,
        "createdAt": now,
        "updatedAt": now,
        "messages": [],
    }
    threads.insert_one(doc)
    return _public(doc)


@router.get("/get/{thread_id}")
def get_messages(thread_id: str, user=Depends(require_user)):
    doc = threads.find_one({"_id": thread_id, "username": user["username"]}, {"messages": 1})
    if not doc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Conversation not found."})
    return doc.get("messages", [])


@router.patch("/update/{thread_id}")
def update_thread(thread_id: str, payload: UpdateThread, user=Depends(require_user)):
    doc = get_owned(thread_id, user["username"])
    if payload.title is not None:
        title = " ".join(payload.title.split())[:120] or doc.get("title")
        threads.update_one({"_id": thread_id}, {"$set": {"title": title}})
        doc["title"] = title
    return _public(doc)


@router.delete("/delete/{thread_id}")
def delete_thread(thread_id: str, user=Depends(require_user)):
    get_owned(thread_id, user["username"])
    threads.delete_one({"_id": thread_id, "username": user["username"]})
    delete_for_thread(thread_id, user["username"])
    return {"ok": True}
