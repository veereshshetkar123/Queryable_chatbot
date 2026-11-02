"""Data catalog admin API: browse collections and add datasets from Excel/CSV.

Admins (browser session, ``role == "admin"``) drop an ``.xlsx`` or ``.csv``
file, see a preview of the detected columns and types, and import it as a
new MongoDB collection. The chatbot picks it up on the next question: schema
discovery is cleared after every import, and uploaded collections are always
queryable, even when ``QUERYABLE_COLLECTIONS`` restricts the sample data.

    GET    /api/catalog                     -> collections, fields, samples, dataset metadata
    POST   /api/catalog/preview             -> parse a file, return columns/types/first rows (no write)
    POST   /api/catalog/upload              -> import a file as a collection
    PATCH  /api/catalog/{name}              -> rename label / edit description
    DELETE /api/catalog/{name}              -> drop an uploaded dataset

Every import, edit and delete is written to the admin audit log. Only
collections created by an upload can be replaced or deleted from here; the
sample collections are protected.
"""

import csv
import io
import re
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.admin import _audit, require_admin
from backend.config import INTERNAL_COLLECTIONS
from backend.db import business_collection_names, db
from backend.guardrails import redact_pii
from backend.schema_discovery import clear_schema_cache, get_schema

router = APIRouter(prefix="/api/catalog", tags=["catalog"])

datasets = db["app_datasets"]

MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_ROWS = 100_000
MAX_COLUMNS = 300
PREVIEW_ROWS = 8
BATCH = 1000
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
ALLOWED_SUFFIXES = (".csv", ".xlsx", ".xlsm")

TRUE_WORDS = {"true", "yes", "y"}
FALSE_WORDS = {"false", "no", "n"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?$")
INT_RE = re.compile(r"^[+-]?\d+$")
FLOAT_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


def ensure_indexes():
    datasets.create_index("name", unique=True)


def _bad(code, message, status=400):
    return HTTPException(status_code=status, detail={"code": code, "message": message})


# --------------------------------------------------
# Parsing
# --------------------------------------------------

def snake(text, fallback):
    """'Annual Revenue ($)' -> 'annual_revenue'. Field names the query agent can use."""

    value = re.sub(r"[^0-9a-zA-Z]+", "_", str(text or "").strip()).strip("_").lower()
    if not value:
        value = fallback
    if value[0].isdigit():
        value = f"c_{value}"
    return value[:64]


def dataset_name(filename):
    stem = re.sub(r"\.[^.]+$", "", filename or "")
    name = snake(stem, "dataset")
    if not name[0].isalpha():
        name = f"d_{name}"
    if len(name) < 2:
        name = f"{name}_data"
    return name[:48]


def _headers(raw):
    seen = {}
    out = []
    for index, header in enumerate(raw, start=1):
        name = snake(header, f"column_{index}")
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        out.append(name)
    return out


def _cell_text(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ") if value.time() != time(0) else value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _decode(content):
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise _bad("bad_file", "The CSV file is not valid text.")


def _read_csv(content):
    text = _decode(content)
    try:
        dialect = csv.Sniffer().sniff(text[:20000], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [row for row in csv.reader(io.StringIO(text), dialect)]


def _read_xlsx(content, sheet=None):
    try:
        from openpyxl import load_workbook
    except ImportError as error:  # pragma: no cover - dependency missing
        raise _bad("unsupported", "Excel support is not installed on the server (openpyxl).", 500) from error
    try:
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as error:  # noqa: BLE001 - any corrupt workbook
        raise _bad("bad_file", "The Excel file could not be read. Save it as .xlsx and try again.") from error
    try:
        names = book.sheetnames
        if sheet and sheet not in names:
            raise _bad("bad_sheet", f"Sheet '{sheet}' was not found. Sheets: {', '.join(names)}.")
        target = book[sheet] if sheet else None
        if target is None:
            # First sheet with data.
            for name in names:
                if book[name].max_row and book[name].max_row > 1:
                    target = book[name]
                    break
            target = target or book[names[0]]
        rows = []
        for row in target.iter_rows(values_only=True):
            rows.append([_cell_text(value) for value in row])
            if len(rows) > MAX_ROWS + 50:
                break
        return rows, names, target.title
    finally:
        book.close()


def _infer(values):
    """Column type from its non-empty text values: int, float, bool, date or str."""

    present = [v for v in values if v != ""]
    if not present:
        return "str"
    if any(len(v) > 1 and v[0] == "0" and v[1].isdigit() for v in present):
        return "str"  # codes and zip codes keep their leading zeros
    if all(INT_RE.match(v.replace(",", "")) for v in present):
        return "int"
    if all(FLOAT_RE.match(v.replace(",", "")) for v in present):
        return "float"
    if all(v.lower() in TRUE_WORDS | FALSE_WORDS for v in present):
        return "bool"
    if all(DATE_RE.match(v) for v in present):
        return "date"
    return "str"


def _convert(value, kind):
    if value == "":
        return None
    try:
        if kind == "int":
            number = int(value.replace(",", ""))
            return number if abs(number) < 2**63 else float(number)
        if kind == "float":
            return float(value.replace(",", ""))
    except ValueError:
        return value
    if kind == "bool":
        return value.lower() in TRUE_WORDS
    return value  # dates stay ISO text: sortable and safe in every response


def parse_upload(filename, content, sheet=None):
    """Turn file bytes into (columns, types, documents, sheet info)."""

    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in (filename or "") else ""
    if suffix not in ALLOWED_SUFFIXES:
        if suffix == ".xls":
            raise _bad("unsupported", "Old .xls files are not supported. Save the file as .xlsx or .csv.")
        raise _bad("unsupported", "Upload an Excel (.xlsx) or CSV (.csv) file.")
    if not content:
        raise _bad("bad_file", "The file is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise _bad("too_large", f"Files up to {MAX_FILE_BYTES // (1024 * 1024)} MB are supported.", 413)

    sheets, sheet_used = [], None
    if suffix == ".csv":
        rows = _read_csv(content)
    else:
        rows, sheets, sheet_used = _read_xlsx(content, sheet)

    rows = [[_cell_text(c) if not isinstance(c, str) else c.strip() for c in row] for row in rows]
    rows = [row for row in rows if any(cell != "" for cell in row)]
    if len(rows) < 2:
        raise _bad("bad_file", "The file needs a header row and at least one data row.")

    width = max(len(row) for row in rows)
    # Drop trailing columns that are empty everywhere (common in Excel exports).
    while width and all(len(row) < width or row[width - 1] == "" for row in rows):
        width -= 1
    if width > MAX_COLUMNS:
        raise _bad("too_large", f"Up to {MAX_COLUMNS} columns are supported.")

    header, body = rows[0], rows[1:]
    if len(body) > MAX_ROWS:
        raise _bad("too_large", f"Up to {MAX_ROWS:,} rows are supported; this file has more.", 413)

    columns = _headers([header[i] if i < len(header) else "" for i in range(width)])
    grid = [[row[i] if i < len(row) else "" for i in range(width)] for row in body]
    types = [_infer([row[i] for row in grid]) for i in range(width)]

    documents = []
    for row in grid:
        doc = {}
        for column, kind, value in zip(columns, types, row):
            converted = _convert(value, kind)
            if converted is not None:
                doc[column] = converted
        if doc:
            documents.append(doc)

    original = [str(header[i]) if i < len(header) else "" for i in range(width)]
    return {
        "columns": [
            {"name": name, "original": orig, "type": kind,
             "filled": sum(1 for row in grid if row[i] != "")}
            for i, (name, orig, kind) in enumerate(zip(columns, original, types))
        ],
        "documents": documents,
        "sheets": sheets,
        "sheet": sheet_used,
    }


# --------------------------------------------------
# Catalog
# --------------------------------------------------

def _meta_by_name():
    return {doc["name"]: doc for doc in datasets.find({}, {"_id": 0})}


def _iso(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return value


def _public_meta(doc):
    if not doc:
        return None
    return {
        "label": doc.get("label"),
        "description": doc.get("description", ""),
        "filename": doc.get("filename"),
        "sheet": doc.get("sheet"),
        "uploaded_by": doc.get("uploaded_by"),
        "uploaded_at": _iso(doc.get("uploaded_at")),
        "rows": doc.get("rows"),
    }


def catalog():
    schema = get_schema()
    meta = _meta_by_name()
    collections = []
    for name in sorted(set(schema) | {n for n in meta if n in business_collection_names()}):
        fields = schema.get(name, {})
        info = meta.get(name)
        collections.append({
            "name": name,
            "documents": db[name].estimated_document_count(),
            "source": "upload" if info else "sample",
            "dataset": _public_meta(info),
            "fields": [{"name": field, "type": details.get("type"),
                        "samples": redact_pii([{field: value} for value in details.get("sample_values", [])])}
                       for field, details in fields.items()],
        })
    return {"collections": collections}


@router.get("")
def get_catalog(admin=Depends(require_admin)):
    """Collections and fields the chatbot can read (PII-masked samples). Admins only."""

    return catalog()


def _check_name(name, mode):
    if not NAME_PATTERN.match(name or ""):
        raise _bad("bad_name", "Use 2-48 lowercase letters, digits or _, starting with a letter.")
    if name in INTERNAL_COLLECTIONS or name.startswith(("app_", "system")):
        raise _bad("bad_name", "That name is reserved by the application.")
    exists = name in db.list_collection_names()
    uploaded = datasets.find_one({"name": name}) is not None
    if exists and not uploaded:
        raise _bad("name_taken", f"'{name}' is a built-in collection and cannot be replaced. Pick another name.", 409)
    if uploaded and mode == "create":
        raise _bad("name_taken", f"A dataset called '{name}' already exists. Choose Replace or Append.", 409)
    return exists


async def _read(file: UploadFile):
    content = await file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise _bad("too_large", f"Files up to {MAX_FILE_BYTES // (1024 * 1024)} MB are supported.", 413)
    return content


@router.post("/preview")
async def preview(
    file: UploadFile = File(...),
    sheet: str | None = Form(None),
    admin=Depends(require_admin),
):
    """Parse the file and show what would be imported, without writing anything."""

    parsed = parse_upload(file.filename, await _read(file), sheet or None)
    suggested = dataset_name(file.filename)
    existing = datasets.find_one({"name": suggested}, {"_id": 0, "name": 1})
    return {
        "filename": file.filename,
        "suggested_name": suggested,
        "exists": bool(existing) or suggested in db.list_collection_names(),
        "rows": len(parsed["documents"]),
        "columns": parsed["columns"],
        "sheets": parsed["sheets"],
        "sheet": parsed["sheet"],
        "preview": parsed["documents"][:PREVIEW_ROWS],
    }


@router.post("/upload", status_code=201)
async def upload(
    file: UploadFile = File(...),
    name: str | None = Form(None),
    label: str | None = Form(None),
    description: str = Form(""),
    sheet: str | None = Form(None),
    mode: str = Form("create"),
    admin=Depends(require_admin),
):
    """Import an Excel/CSV file as a queryable collection."""

    if mode not in {"create", "replace", "append"}:
        raise _bad("bad_request", "mode must be create, replace or append.")
    name = (name or dataset_name(file.filename)).strip().lower()
    _check_name(name, mode)
    parsed = parse_upload(file.filename, await _read(file), sheet or None)
    documents = parsed["documents"]
    if not documents:
        raise _bad("bad_file", "No rows with values were found.")

    collection = db[name]
    if mode in {"create", "replace"}:
        collection.drop()
    for start in range(0, len(documents), BATCH):
        collection.insert_many(documents[start:start + BATCH], ordered=False)

    now = datetime.now(timezone.utc)
    total = collection.count_documents({})
    clean_label = (label or "").strip()[:80] or name.replace("_", " ").title()
    datasets.update_one(
        {"name": name},
        {
            "$set": {
                "label": clean_label,
                "description": description.strip()[:500],
                "filename": file.filename,
                "sheet": parsed["sheet"],
                "columns": [{"name": c["name"], "type": c["type"]} for c in parsed["columns"]],
                "rows": total,
                "uploaded_by": admin["username"],
                "uploaded_at": now,
            },
            "$setOnInsert": {"name": name, "created_at": now},
        },
        upsert=True,
    )
    clear_schema_cache()
    _audit(admin, "dataset.upload", name,
           {"filename": file.filename, "rows": len(documents), "mode": mode, "columns": len(parsed["columns"])})
    return {
        "name": name,
        "label": clean_label,
        "rows_imported": len(documents),
        "rows_total": total,
        "columns": parsed["columns"],
        "mode": mode,
    }


class DatasetPatch(BaseModel):
    label: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=500)


def _uploaded(name):
    doc = datasets.find_one({"name": name})
    if not doc:
        raise _bad("not_found", "Only uploaded datasets can be changed here.", 404)
    return doc


@router.patch("/{name}")
def update_dataset(name: str, payload: DatasetPatch, admin=Depends(require_admin)):
    _uploaded(name)
    changes = {key: value.strip() for key, value in payload.model_dump(exclude_none=True).items()}
    if changes:
        datasets.update_one({"name": name}, {"$set": changes})
        _audit(admin, "dataset.update", name, changes)
    return {"name": name, "dataset": _public_meta(datasets.find_one({"name": name}))}


@router.delete("/{name}")
def delete_dataset(name: str, admin=Depends(require_admin)):
    doc = _uploaded(name)
    db[name].drop()
    datasets.delete_one({"name": name})
    clear_schema_cache()
    _audit(admin, "dataset.delete", name, {"rows": doc.get("rows"), "filename": doc.get("filename")})
    return {"deleted": name}


def uploaded_names():
    try:
        return set(datasets.distinct("name"))
    except Exception:  # noqa: BLE001 - MongoDB down: callers handle it
        return set()
