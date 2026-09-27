import os

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent

from langchain_tools import query_mongodb


load_dotenv()


llm = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash",
    temperature=0,
    google_api_key=os.getenv("GEMINI_API_KEY")
)


agent = create_agent(
    model=llm,
    tools=[query_mongodb],
    system_prompt="""
You are a queryable database assistant for an e-commerce sales and customer analysis database.

The MongoDB database contains these collections and fields:

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

Use the collection that is relevant to the user's question.

When using the query_mongodb tool, you MUST provide the query as a JSON string.

For a normal lookup, use this structure:

{
    "collection": "customers",
    "operation": "find",
    "filters": {},
    "fields": [
        "customer_id",
        "country",
        "signup_date"
    ]
}

For aggregation questions, use:

{
    "collection": "sales_cleaned",
    "operation": "aggregate",
    "pipeline": []
}

Choose the correct collection and fields based on the user's question.

Do not use collections or fields that are not listed above.

For questions about total revenue, total quantity, highest revenue, lowest revenue, averages, grouping, sorting, or top products, use an aggregation query when appropriate.

For example, if the user asks:

"show total revenue by product"

use the sales_cleaned collection and an aggregation pipeline.

For example:

{
    "collection": "sales_cleaned",
    "operation": "aggregate",
    "pipeline": [
        {
            "$group": {
                "_id": "$product_id",
                "total_revenue": {
                    "$sum": "$Revenue"
                }
            }
        },
        {
            "$sort": {
                "total_revenue": -1
            }
        }
    ]
}

Only use information returned by MongoDB.

Do not invent data.

Give the user a simple and clear answer based on the database results.
"""
)


def run_langchain_agent(question):
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": question
                }
            ]
        }
    )

    messages = result.get("messages", [])

    if not messages:
        return "No response was generated."

    last_message = messages[-1]

    content = getattr(last_message, "content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []

        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))

        if text_parts:
            return "\n".join(text_parts)

    return str(content)