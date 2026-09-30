import json

from langchain_core.tools import tool

from backend.database_tool import run_database_query
from backend.validator import validate_query


@tool
def query_mongodb(query: str) -> str:
    """
    Run a validated read-only query against MongoDB.
    The query must be provided as a JSON string.
    """

    try:
        query_data = json.loads(query)
    except json.JSONDecodeError:
        return "invalid query format"

    if not validate_query(query_data):
        return "query validation failed"

    result = run_database_query(query_data)

    return json.dumps(result, default=str)