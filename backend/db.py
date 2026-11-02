"""Shared MongoDB client.

One client is reused by the query tool, schema discovery, authentication and
thread storage, so connection settings live in one place.
"""

from pymongo import MongoClient

from backend.config import INTERNAL_COLLECTIONS, settings

client = MongoClient(
    settings.mongodb_uri,
    # Fail fast when MongoDB is down, so the UI can say so instead of hanging.
    serverSelectionTimeoutMS=3000,
    connectTimeoutMS=5000,
)

db = client[settings.mongodb_db]


def business_collection_names():
    """Collections the chatbot is allowed to read for analytics."""

    names = [
        name
        for name in db.list_collection_names()
        if name not in INTERNAL_COLLECTIONS and not name.startswith("system.")
    ]

    if settings.queryable_collections:
        # Datasets an admin uploaded from the Data catalog are always
        # queryable; the allowlist only narrows the other collections.
        allowed = set(settings.queryable_collections) | set(db["app_datasets"].distinct("name"))
        names = [name for name in names if name in allowed]

    return sorted(names)


def ping():
    client.admin.command("ping")
    return True
