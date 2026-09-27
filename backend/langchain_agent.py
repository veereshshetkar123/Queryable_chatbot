import json
from dotenv import load_dotenv
from langchain_openrouter import ChatOpenRouter
from langchain_tools import query_mongodb

load_dotenv()


llm = ChatOpenRouter(
    model="google/gemini-2.5-flash",
    temperature=0
)


def run_langchain_agent(question):

    schema = """
MongoDB database: queryable_chatbot

Main collections:

customers:
- customer_id
- country
- signup_date

products:
- product_id
- product_name
- category

orders:
- order_id
- customer_id
- order_date
- status

order_items:
- order_id
- product_id
- quantity
- price

sales_cleaned:
- order_id
- product_id
- quantity
- price
- Revenue
- customer_id
- order_date
- year
- month
"""

    query_prompt = f"""
You are a database query agent.

{schema}

The user asked:

{question}

Create ONE valid MongoDB query for the user's question.

Return ONLY valid JSON.
Do not use markdown.
Do not use ```json.
Do not add explanations.

For a count question use:

{{
    "collection": "customers",
    "operation": "count",
    "filters": {{}}
}}

For a normal lookup use:

{{
    "collection": "customers",
    "operation": "find",
    "filters": {{}},
    "fields": ["customer_id", "country", "signup_date"]
}}

For aggregation use:

{{
    "collection": "sales_cleaned",
    "operation": "aggregate",
    "pipeline": [
        {{
            "$group": {{
                "_id": "$product_id",
                "total_revenue": {{
                    "$sum": "$Revenue"
                }}
            }}
        }}
    ]
}}

Use only the collections and fields listed above.

Do not invent collections or fields.
"""

    # Ask OpenRouter to create the MongoDB query
    query_response = llm.invoke(query_prompt).content

    # Convert list responses to text if necessary
    if isinstance(query_response, list):
        query_response = "".join(
            item.get("text", "")
            for item in query_response
            if isinstance(item, dict)
        )

    query_response = query_response.strip()

    # Remove markdown code fences if the model returns them
    if query_response.startswith("```"):
        query_response = query_response.replace("```json", "")
        query_response = query_response.replace("```", "")
        query_response = query_response.strip()

    try:
        query_data = json.loads(query_response)
    except json.JSONDecodeError:
        return "The AI did not return a valid database query."

    # Execute the MongoDB query
    result = query_mongodb.invoke(
        json.dumps(query_data)
    )

    # Create the final user-friendly answer
    answer_prompt = f"""
You are a database assistant.

User question:
{question}

MongoDB result:
{result}

Answer the user's question using ONLY the MongoDB result.

Do not invent information.

Give a simple and clear answer.
"""

    # Ask OpenRouter to create the final answer
    answer = llm.invoke(answer_prompt).content

    return answer