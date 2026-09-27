import json

from schema_discovery import get_schema
from gemini_rest import ask_gemini


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
            "properties": {}
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

- Use only collections that exist in the schema.
- Use only fields that exist in the schema.
- Do not invent field names.
- Use operation "find" for normal lookup questions.
- Use operation "count" when the user asks how many records there are.
- If the user gives a condition, put it inside filters.
- Use the user's requested values in the filters.
- Return ONLY valid JSON.
- Do not add markdown.
- Do not add explanations.

Return exactly this structure:

{{
    "collection": "collection_name",
    "operation": "find",
    "filters": {{}},
    "fields": []
}}
"""

    response = ask_gemini(prompt)

    response = response.strip()

    if response.startswith("```"):
        response = response.replace("```json", "")
        response = response.replace("```", "")
        response = response.strip()

    try:
        query = json.loads(response)
    except json.JSONDecodeError:
        raise ValueError("Gemini returned invalid JSON")

    return json.dumps(query)


if __name__ == "__main__":
    question = "show customers"

    result = understand_question(question)

    print(result)