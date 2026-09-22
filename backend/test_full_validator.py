from validator import validate_query


query = {
    "collection": "employees",
    "operation": "find",
    "filters": {
        "department": "ai",
        "city": "bangalore"
    },
    "fields": [
        "employee_id",
        "employee_name",
        "department",
        "city",
        "designation"
    ]
}


result = validate_query(query)

print("query is valid:", result)