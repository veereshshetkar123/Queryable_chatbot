"""Saved artifacts: the charts, maps, insight cards and queries behind answers.

Every database answer produces structured tool results (``visual_analysis``,
``geo_map``, ``data_insights``, ``query_mongodb``). The chat already shows
them inline; this module also keeps a copy per user so they can be found
again later, outside the conversation, in the sidebar's Artifacts library.

Implements the ``ArtifactStorage`` contract of ``@openuidev/react-headless``
(the frontend client is ``openui_test/src/lib/artifact-storage.ts``):

    GET    /api/artifacts?name=&type=a,b&cursor=&limit=  -> {"artifacts": [...], "nextCursor"?}
    GET    /api/artifacts/{id}                           -> Artifact (with content)
    PATCH  /api/artifacts/{id}   {"title"?, "content"?}  -> ArtifactSummary
    DELETE /api/artifacts/{id}

Stored ``content`` has the same shape as the tool result the frontend
renderer parses, so a saved artifact renders exactly like the live one.
Every artifact belongs to the signed-in user; another user's artifact is
reported as not found.
"""

import json
import re
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth import require_user
from backend.db import db
from backend.observability import logger

artifacts = db["app_artifacts"]

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])

# Tool name -> artifact type (the `type` of the matching frontend renderer).
TOOL_TYPES = {
    "visual_analysis": "qc_visual_analysis",
    "geo_map": "qc_geo_map",
    "data_insights": "qc_data_insights",
    "query_mongodb": "qc_mongodb_query",
}
TYPES = frozenset(TOOL_TYPES.values())

PAGE_SIZE = 24
MAX_PAGE_SIZE = 100
MAX_CONTENT_BYTES = 512 * 1024
MAX_TITLE = 120


def ensure_indexes():
    artifacts.create_index([("username", 1), ("updatedAt", -1), ("_id", -1)])
    artifacts.create_index([("username", 1), ("threadId", 1)])


def _now_ms():
    return int(time.time() * 1000)


def _summary(doc):
    return {
        "id": doc["_id"],
        "title": doc.get("title") or "Untitled",
        "type": doc["type"],
        "threadId": doc.get("threadId") or "",
        "updatedAt": doc.get("updatedAt"),
    }


def _not_found():
    return HTTPException(status_code=404, detail={"code": "not_found", "message": "Artifact not found."})


def _clean_title(text):
    return " ".join(str(text or "").split())[:MAX_TITLE]


def build_artifacts(username, thread_id, question, calls):
    """Artifact documents for one chat run.

    ``calls`` is a list of ``(tool_name, args, result)``. Tools without an
    artifact type, failed queries and oversized results are skipped.
    """

    now = _now_ms()
    title = _clean_title(question) or "Untitled analysis"
    docs = []
    for index, (name, args, result) in enumerate(calls):
        kind = TOOL_TYPES.get(name)
        if not kind or not isinstance(result, dict):
            continue
        if kind == "qc_mongodb_query":
            if result.get("ok") is False:
                continue
            # The query renderer reads the executed query from the tool-call
            # args, which a stored artifact does not have; keep it in content.
            content = {**result, "query": args}
        else:
            content = result
        try:
            size = len(json.dumps(content, default=str))
        except (TypeError, ValueError):
            continue
        if size > MAX_CONTENT_BYTES:
            continue
        docs.append(
            {
                "_id": str(uuid.uuid4()),
                "username": username,
                "threadId": thread_id,
                "type": kind,
                "tool": name,
                "title": title,
                "question": question,
                # Later artifacts of a run sort first, matching the answer order.
                "createdAt": now + index,
                "updatedAt": now + index,
                "content": json.loads(json.dumps(content, default=str)),
            }
        )
    return docs


def save_run_artifacts(username, thread_id, question, calls):
    docs = build_artifacts(username, thread_id, question, calls)
    if docs:
        artifacts.insert_many(docs)
    return len(docs)


def delete_for_thread(thread_id, username):
    try:
        artifacts.delete_many({"threadId": thread_id, "username": username})
    except Exception:  # noqa: BLE001 - never block deleting a conversation
        logger.warning("could not delete artifacts of thread %s", thread_id, exc_info=True)


class ArtifactPatch(BaseModel):
    id: str | None = None
    title: str | None = None
    content: dict | None = None


@router.get("")
def list_artifacts(
    name: str | None = None,
    type: str | None = None,  # noqa: A002 - matches the ArtifactStorage contract
    cursor: str | None = None,
    limit: int = PAGE_SIZE,
    user=Depends(require_user),
):
    query = {"username": user["username"]}
    if name and name.strip():
        query["title"] = {"$regex": re.escape(name.strip()[:100]), "$options": "i"}
    if type:
        wanted = [kind for kind in (part.strip() for part in type.split(",")) if kind in TYPES]
        query["type"] = {"$in": wanted}
    if cursor:
        # "<updatedAt>:<id>" of the last item; the id breaks timestamp ties.
        stamp, _, last_id = cursor.partition(":")
        try:
            stamp = int(stamp)
        except ValueError:
            raise HTTPException(status_code=400, detail={"code": "bad_cursor", "message": "Invalid cursor."})
        query["$or"] = [{"updatedAt": {"$lt": stamp}}, {"updatedAt": stamp, "_id": {"$lt": last_id}}]

    size = max(1, min(int(limit or PAGE_SIZE), MAX_PAGE_SIZE))
    docs = list(
        artifacts.find(query, {"content": 0}).sort([("updatedAt", -1), ("_id", -1)]).limit(size + 1)
    )
    result = {"artifacts": [_summary(doc) for doc in docs[:size]]}
    if len(docs) > size:
        last = docs[size - 1]
        result["nextCursor"] = f"{last['updatedAt']}:{last['_id']}"
    return result


@router.get("/{artifact_id}")
def get_artifact(artifact_id: str, user=Depends(require_user)):
    doc = artifacts.find_one({"_id": artifact_id, "username": user["username"]})
    if not doc:
        raise _not_found()
    return {**_summary(doc), "content": doc.get("content")}


@router.patch("/{artifact_id}")
def update_artifact(artifact_id: str, payload: ArtifactPatch, user=Depends(require_user)):
    doc = artifacts.find_one({"_id": artifact_id, "username": user["username"]}, {"content": 0})
    if not doc:
        raise _not_found()
    update = {"updatedAt": _now_ms()}
    if payload.title is not None:
        update["title"] = _clean_title(payload.title) or doc.get("title")
    if payload.content is not None:
        if len(json.dumps(payload.content, default=str)) > MAX_CONTENT_BYTES:
            raise HTTPException(status_code=413, detail={"code": "too_large", "message": "Artifact is too large."})
        update["content"] = payload.content
    artifacts.update_one({"_id": artifact_id}, {"$set": update})
    doc.update(update)
    return _summary(doc)


@router.delete("/{artifact_id}")
def delete_artifact(artifact_id: str, user=Depends(require_user)):
    result = artifacts.delete_one({"_id": artifact_id, "username": user["username"]})
    if not result.deleted_count:
        raise _not_found()
    return {"ok": True}
