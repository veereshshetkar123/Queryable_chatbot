from query_executor import execute_query


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


result = execute_query(query)

print("database result:")
print(result)