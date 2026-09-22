from llm import ask_gemini


schema = {
    "type": "object",
    "properties": {
        "collection": {
            "type": "string"
        },
        "filters": {
            "type": "object",
            "properties": {
                "department": {
                    "type": "string"
                },
                "city": {
                    "type": "string"
                }
            }
        },
        "fields": {
            "type": "array",
            "items": {
                "type": "string"
            }
        }
    },
    "required": ["collection", "filters", "fields"]
}


question = """
The user wants to show AI employees in Bangalore.
Return the relevant MongoDB collection, filters, and fields.
"""


answer = ask_gemini(question, response_schema=schema)

print(answer)