"""Data catalog admin: Excel/CSV upload, permissions, agent map."""

import io

import pytest

from backend import admin, data_catalog
from backend.auth import create_user, sessions, users
from backend.db import business_collection_names, db
from backend.schema_discovery import get_schema

ADMIN = {"username": "catboss", "password": "admin-password-123"}

CSV = (
    "Region,Units Sold,Revenue ($),Zip Code,Active,Order Date\n"
    "North,10,1500.50,01234,yes,2024-01-05\n"
    "South,7,980,02111,no,2024-02-11\n"
    "North,,1200.25,03000,yes,2024-03-01\n"
).encode()


@pytest.fixture()
def admin_client(app_client, user):
    users.delete_many({"username": ADMIN["username"]})
    create_user(ADMIN["username"], ADMIN["password"], "Cat Boss", role="admin")
    assert app_client.post("/api/auth/login", json=ADMIN).status_code == 200
    yield app_client
    for doc in data_catalog.datasets.find({}, {"name": 1}):
        db[doc["name"]].drop()
    data_catalog.datasets.delete_many({})
    users.delete_many({"username": ADMIN["username"]})
    sessions.delete_many({"username": ADMIN["username"]})
    admin.audit_log.delete_many({})


def _file(name="Regional Sales.csv", content=CSV, kind="text/csv"):
    return {"file": (name, io.BytesIO(content), kind)}


def test_analysts_cannot_see_or_change_the_catalog(logged_in):
    assert logged_in.get("/api/catalog").status_code == 403
    assert logged_in.post("/api/catalog/upload", files=_file()).status_code == 403
    assert logged_in.get("/api/admin/agents").status_code == 403
    assert logged_in.get("/api/admin/integrations").status_code == 403


def test_preview_detects_columns_and_types(admin_client):
    body = admin_client.post("/api/catalog/preview", files=_file()).json()
    assert body["suggested_name"] == "regional_sales"
    assert body["rows"] == 3
    types = {c["name"]: c["type"] for c in body["columns"]}
    assert types == {"region": "str", "units_sold": "int", "revenue": "float",
                     "zip_code": "str", "active": "bool", "order_date": "date"}
    assert body["preview"][0] == {"region": "North", "units_sold": 10, "revenue": 1500.5,
                                  "zip_code": "01234", "active": True, "order_date": "2024-01-05"}
    # Empty cells are left out, not stored as "".
    assert "units_sold" not in body["preview"][2]
    assert "regional_sales" not in db.list_collection_names()


def test_upload_makes_a_queryable_dataset(admin_client):
    created = admin_client.post("/api/catalog/upload", files=_file(),
                                data={"description": "Q1 regional sales"})
    assert created.status_code == 201, created.text
    assert created.json()["rows_total"] == 3

    assert "regional_sales" in business_collection_names()
    assert "revenue" in get_schema()["regional_sales"]

    listed = {c["name"]: c for c in admin_client.get("/api/catalog").json()["collections"]}
    assert listed["regional_sales"]["source"] == "upload"
    assert listed["regional_sales"]["dataset"]["description"] == "Q1 regional sales"
    assert listed["span_companies"]["source"] == "sample"

    # Same name again needs an explicit mode.
    assert admin_client.post("/api/catalog/upload", files=_file()).status_code == 409
    appended = admin_client.post("/api/catalog/upload", files=_file(), data={"mode": "append"}).json()
    assert appended["rows_total"] == 6
    replaced = admin_client.post("/api/catalog/upload", files=_file(), data={"mode": "replace"}).json()
    assert replaced["rows_total"] == 3

    patched = admin_client.patch("/api/catalog/regional_sales", json={"label": "Sales by region"}).json()
    assert patched["dataset"]["label"] == "Sales by region"

    assert admin_client.delete("/api/catalog/regional_sales").status_code == 200
    assert "regional_sales" not in db.list_collection_names()
    actions = [e["action"] for e in admin_client.get("/api/admin/audit").json()["events"]]
    assert {"dataset.upload", "dataset.update", "dataset.delete"} <= set(actions)


def test_excel_upload(admin_client):
    openpyxl = pytest.importorskip("openpyxl")
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Deals"
    sheet.append(["Account", "Amount", "Closed"])
    sheet.append(["Acme", 1200, True])
    sheet.append(["Globex", 300.5, False])
    buffer = io.BytesIO()
    book.save(buffer)
    content = buffer.getvalue()
    kind = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    body = admin_client.post("/api/catalog/preview", files=_file("deals.xlsx", content, kind)).json()
    assert body["sheets"] == ["Deals"] and body["rows"] == 2
    created = admin_client.post("/api/catalog/upload", files=_file("deals.xlsx", content, kind)).json()
    assert created["name"] == "deals"
    assert db["deals"].find_one({"account": "Acme"}, {"_id": 0}) == {"account": "Acme", "amount": 1200, "closed": True}


def test_built_in_collections_are_protected(admin_client):
    taken = admin_client.post("/api/catalog/upload", files=_file(), data={"name": "span_companies", "mode": "replace"})
    assert taken.status_code == 409
    assert admin_client.post("/api/catalog/upload", files=_file(), data={"name": "app_users"}).status_code == 400
    assert admin_client.delete("/api/catalog/span_companies").status_code == 404
    assert db["span_companies"].count_documents({}) > 0


def test_rejects_bad_files(admin_client):
    assert admin_client.post("/api/catalog/preview", files=_file("x.xls", b"abc")).status_code == 400
    assert admin_client.post("/api/catalog/preview", files=_file("x.csv", b"only,header\n")).status_code == 400
    assert admin_client.post("/api/catalog/preview", files=_file("x.pdf", b"%PDF")).status_code == 400


def test_agent_map_includes_uploaded_data(admin_client):
    admin_client.post("/api/catalog/upload", files=_file())
    body = admin_client.get("/api/admin/agents").json()
    ids = {a["id"] for a in body["agents"]}
    assert {"router", "query", "validator", "executor", "answer", "ingest"} <= ids
    data = {d["name"]: d for d in body["data"]}
    assert data["regional_sales"]["kind"] == "upload"
    ingest = next(a for a in body["agents"] if a["id"] == "ingest")
    assert "data:regional_sales" in ingest["writes"]
    assert any(e["from"] == "validator" and e["to"] == "executor" for e in body["edges"])

    integrations = admin_client.get("/api/admin/integrations").json()
    assert any(c["recommended"] for c in integrations["candidates"])
