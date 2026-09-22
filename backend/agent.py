from schema_discovery import get_schema
from llm import ask_gemini


query_schema = {
    "type": "object",
    "properties": {
        "collection": {
            "type": "string"
        },
        "operation": {
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
    "required": [
        "collection",
        "operation",
        "filters",
        "fields"
    ]
}


def understand_question(question):
    schema = get_schema()

    prompt = f"""
You are a database query assistant.

MongoDB database schema:
{schema}

User question:
{question}

Create a MongoDB read query based only on the available
collections and fields in the schema.

Rules:
- Use only fields that exist in the schema.
- Do not invent field names.
- Use operation "find".
- If the user mentions a condition such as department or city,
  put that condition inside filters.
- Do not leave filters empty when the user has given a condition.
- Use the user's requested values in the filters.
- For fields, use only fields that actually exist in the schema.
- Return only the required structured JSON.
"""

    return ask_gemini(
        prompt,
        response_schema=query_schema
    )


if __name__ == "__main__":
    question = "show ai employees in bangalore"

    result = understand_question(question)

    print("generated query:")
    print(result)