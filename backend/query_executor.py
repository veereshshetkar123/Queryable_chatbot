from validator import validate_query
from database_tool import run_database_query


def execute_query(query):
    print("validating query...")

    if not validate_query(query):
        return {
            "error": "query validation failed"
        }

    print("query is valid")
    print("running database query...")

    result = run_database_query(query)

    return result