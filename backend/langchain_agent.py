import json
from dotenv import load_dotenv
from langchain_openrouter import ChatOpenRouter
from langchain_tools import query_mongodb

load_dotenv()


llm = ChatOpenRouter(
    model="google/gemini-2.5-flash",
    temperature=0
)


def is_database_question(question):
    router_prompt = f"""
Decide whether the user's question requires information from the MongoDB database.

User question:
{question}

Return ONLY one word:
DATABASE
or
GENERAL

DATABASE = the question asks about customers, products, orders, sales,
revenue, quantities, or other information stored in the database.

GENERAL = normal questions, explanations, definitions, coding questions,
general knowledge, greetings, or other questions that do not require
the MongoDB database.
"""

    response = llm.invoke(router_prompt).content

    if isinstance(response, list):
        response = "".join(
            item.get("text", "")
            for item in response
            if isinstance(item, dict)
        )

    return response.strip().upper().startswith("DATABASE")


def run_langchain_agent(question):

    # --------------------------------------------------
    # STEP 1: Decide whether this is a database question
    # --------------------------------------------------

    if not is_database_question(question):

        general_prompt = f"""
You are a helpful general-purpose AI assistant.

Answer the user's question clearly and naturally.

User question:
{question}

Give a simple and useful answer.
Do not invent facts.
"""

        answer = llm.invoke(general_prompt).content

        if isinstance(answer, list):
            answer = "".join(
                item.get("text", "")
                for item in answer
                if isinstance(item, dict)
            )

        return answer


    # --------------------------------------------------
    # STEP 2: Database question
    # --------------------------------------------------

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

    # --------------------------------------------------
    # STEP 3: Execute MongoDB query
    # --------------------------------------------------

    result = query_mongodb.invoke(
        json.dumps(query_data)
    )

    # --------------------------------------------------
    # STEP 4: Create final database answer
    # --------------------------------------------------

    answer_prompt = f"""
You are a database assistant.

User question:
{question}

MongoDB result:
{result}

Answer the user's question using the MongoDB result.

Do not invent information.

Give a simple and clear answer.
"""

    answer = llm.invoke(answer_prompt).content

    if isinstance(answer, list):
        answer = "".join(
            item.get("text", "")
            for item in answer
            if isinstance(item, dict)
        )

    return answer