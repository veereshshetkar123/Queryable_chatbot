import json

from langchain_core.tools import tool

from validator import validate_query
from database_tool import run_database_query


@tool
def query_mongodb(query: str) -> str:
    """
    Execute a validated MongoDB query.
    The query must be provided as JSON.
    """

    try:
        query_data = json.loads(query)

    except json.JSONDecodeError:
        return "invalid query format"

    if not validate_query(query_data):
        return "query validation failed"

    result = run_database_query(query_data)

    return json.dumps(result, default=str)