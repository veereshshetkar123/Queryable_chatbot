from langchain_tools import query_mongodb


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


result = query_mongodb.invoke({
    "query": str(query).replace("'", '"')
})

print("langchain tool result:")
print(result)