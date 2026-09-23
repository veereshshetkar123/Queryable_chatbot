from database_tool import run_database_query

query = {
    "collection": "employees",
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


result = run_database_query(query)

print("employees result:")
print(result)