"""Agent map and integrations (admin only).

    GET /api/admin/agents        -> every agent in the system, the data each one
                                    sits on, and how they hand off to each other
    GET /api/admin/integrations  -> tools the agent connects to today, and the
                                    candidates for the next integration

The map is built from the live configuration and database, so it changes
when a dataset is uploaded or an optional service (Graphiti, Langfuse) is
switched on.
"""

from fastapi import APIRouter, Depends

from backend.admin import require_admin
from backend.config import SEPARATE_DATASET_COLLECTIONS, settings
from backend.data_catalog import uploaded_names
from backend.db import business_collection_names, db
from backend.schema_discovery import get_schema

router = APIRouter(prefix="/api/admin", tags=["agents"])

GEO_HINTS = ("country", "city", "state", "region", "location")


def _collections():
    schema = get_schema()
    uploads = uploaded_names()
    out = []
    for name in business_collection_names():
        fields = list(schema.get(name, {}))
        if name in uploads:
            kind = "upload"
        elif name in SEPARATE_DATASET_COLLECTIONS:
            kind = "hr"
        else:
            kind = "sample"
        out.append({
            "id": f"data:{name}",
            "name": name,
            "documents": db[name].estimated_document_count(),
            "fields": len(fields),
            "kind": kind,
            "geo": any(hint in field.lower() for field in fields for hint in GEO_HINTS),
        })
    return out


def agent_map():
    collections = _collections()
    every = [c["id"] for c in collections]
    geo = [c["id"] for c in collections if c["geo"]]
    dashboards = [c["id"] for c in collections if c["kind"] in {"sample", "hr"}]
    uploads = [c["id"] for c in collections if c["kind"] == "upload"]
    llm = bool(settings.openrouter_api_key)

    agents = [
        {"id": "guardrails", "name": "Guardrails", "stage": "input",
         "role": "Checks size, prompt injection and write intent; masks PII in every answer.",
         "model": None, "status": "live", "reads": []},
        {"id": "router", "name": "Jev router", "stage": "routing",
         "role": "Decides whether a question needs the database or is general chat. "
                 "Falls back to a LangChain classifier.",
         "model": settings.jev_model if settings.jev_enabled else settings.agent_model,
         "status": "live" if llm else "needs_key", "reads": []},
        {"id": "query", "name": "Query agent", "stage": "reasoning",
         "role": "Turns the question into a MongoDB find / count / distinct / aggregate from the discovered schema.",
         "model": settings.agent_model, "status": "live" if llm else "needs_key", "reads": every},
        {"id": "validator", "name": "Query validator", "stage": "safety",
         "role": "Allowlists collections, fields, operators and aggregation stages; rejects writes.",
         "model": None, "status": "live", "reads": every},
        {"id": "executor", "name": "MongoDB executor", "stage": "data",
         "role": "Runs the validated query read-only with a time and row limit.",
         "model": None, "status": "live", "reads": every},
        {"id": "answer", "name": "Answer agent (OpenUI)", "stage": "response",
         "role": "Writes the reply as streamed UI: text, tables and charts, shown in the artifact panel.",
         "model": settings.openui_model, "status": "live" if llm else "needs_key", "reads": []},
        {"id": "geo", "name": "Geo agent", "stage": "analysis",
         "role": "Finds places in the result and draws them on the globe.",
         "model": None, "status": "live", "reads": geo},
        {"id": "insights", "name": "Insights agent", "stage": "analysis",
         "role": "Deterministic KPIs, statistics and insight cards for the dashboards and answers.",
         "model": None, "status": "live", "reads": dashboards},
        {"id": "ingest", "name": "Dataset ingest", "stage": "data",
         "role": "Turns an uploaded Excel or CSV file into a typed, queryable collection.",
         "model": None, "status": "live", "reads": [], "writes": uploads},
        {"id": "memory", "name": "Graphiti memory", "stage": "context",
         "role": "Knowledge-graph context from past conversations (Neo4j).",
         "model": None, "status": "live" if settings.graphiti_enabled else "off", "reads": []},
    ]

    handoffs = [
        ("guardrails", "router", "safe question"),
        ("router", "query", "database question"),
        ("router", "answer", "general chat"),
        ("memory", "query", "context"),
        ("query", "validator", "MongoDB query"),
        ("validator", "executor", "approved query"),
        ("validator", "query", "rejected: retry"),
        ("executor", "geo", "rows"),
        ("executor", "insights", "rows"),
        ("executor", "answer", "rows"),
        ("geo", "answer", "map"),
        ("insights", "answer", "insights"),
    ]
    return {
        "agents": agents,
        "data": collections,
        "edges": [{"from": a, "to": b, "label": label} for a, b, label in handoffs],
    }


@router.get("/agents")
def get_agents(admin=Depends(require_admin)):
    return agent_map()


def integrations():
    llm = bool(settings.openrouter_api_key)
    live = [
        {"id": "excel", "name": "Excel / CSV upload", "category": "Data in",
         "status": "live", "detail": "Admins drop a file in the Data catalog or on the chat; it becomes a dataset."},
        {"id": "rest", "name": "REST API", "category": "Data out",
         "status": "live", "detail": "POST /api/ask with a personal key (Settings → API keys). Any tool that can call a URL can use it."},
        {"id": "mongodb", "name": "MongoDB / Atlas", "category": "Database",
         "status": "live", "detail": "Read-only query access to every business collection."},
        {"id": "openrouter", "name": "OpenRouter LLMs", "category": "Models",
         "status": "live" if llm else "needs_key", "detail": f"Default model {settings.openui_model}; switchable per chat."},
        {"id": "langfuse", "name": "Langfuse tracing", "category": "Observability",
         "status": "live" if settings.langfuse_public_key and settings.langfuse_secret_key else "available",
         "detail": "Set LANGFUSE_* keys to trace every LLM call."},
    ]
    candidates = [
        {"id": "mcp", "name": "MCP server", "effort": "S", "impact": "High", "recommended": True,
         "why": "Exposes 'ask the database' as a tool any MCP client can call (Claude, Cursor, other agents). "
                "Wraps the existing /ask endpoint and API keys, so it is the smallest step that makes this a "
                "database agent other agents can use."},
        {"id": "slack", "name": "Slack / Teams bot", "effort": "M", "impact": "High",
         "why": "Ask questions from the channel the team already lives in; answers come back as text + a link "
                "to the full artifact."},
        {"id": "gsheets", "name": "Google Sheets / OneDrive sync", "effort": "M", "impact": "Medium",
         "why": "Keeps an uploaded dataset in sync with a live spreadsheet instead of one-off uploads."},
        {"id": "crm", "name": "CRM connector (HubSpot / Salesforce)", "effort": "L", "impact": "High",
         "why": "Pull accounts and deals in as datasets so SPAN data can be joined with pipeline data."},
        {"id": "webhook", "name": "Scheduled reports / webhooks", "effort": "S", "impact": "Medium",
         "why": "Run a saved question on a schedule and post the result to email or a webhook."},
    ]
    return {"live": live, "candidates": candidates}


@router.get("/integrations")
def get_integrations(admin=Depends(require_admin)):
    return integrations()
