import asyncio
import os

from dotenv import load_dotenv

from graphiti_service import GraphitiService


load_dotenv()


group_id = "queryable_chatbot_default"

project_context = """
The Queryable Chatbot project uses the following technology architecture.

MongoDB:
MongoDB is the primary database for structured business data. It stores the
actual business records that the queryable agent retrieves and analyzes.

Neo4j:
Neo4j is the graph database used by Graphiti to store graph-based knowledge,
entities, and relationships.

Graphiti:
Graphiti is the knowledge graph and contextual memory layer. It stores useful
project context, relationships, and conversation information and retrieves
relevant context for later questions.

LangChain:
LangChain is used to build the queryable agent. It interprets user questions,
works with the database tools, and retrieves information from MongoDB.

Jev:
Jev is used as a backend routing and verification component. It helps decide
which path should handle a user request, such as a database query or general
conversation.

FastAPI:
FastAPI is the backend web framework. It receives requests from the OpenUI
frontend and connects the frontend request to Jev, Graphiti, and the
LangChain queryable agent.

Gemini:
Gemini is the large language model used by the application for understanding
and generating responses.

OpenRouter:
OpenRouter is the API gateway used to access the configured language models,
including Gemini, from the backend.

OpenUI:
OpenUI is the frontend presentation layer. It displays chatbot responses,
tables, charts, and other structured output to the user.

Overall architecture:
The user sends a question through OpenUI. OpenUI sends the request to the
FastAPI backend. FastAPI uses Jev for routing and Graphiti for relevant
context. The LangChain queryable agent handles database-related questions
and retrieves exact structured data from MongoDB. Graphiti uses Neo4j as its
graph database backend for contextual knowledge and relationships. Gemini is
used as the language model through OpenRouter. The final answer is returned
to OpenUI for presentation.

MongoDB remains the source for exact structured business data.
Graphiti and Neo4j provide contextual knowledge and relationships.
OpenUI provides the user-facing presentation layer.
"""


async def main():
    neo4j_password = os.getenv("NEO4J_PASSWORD")

    if not neo4j_password:
        raise ValueError("NEO4J_PASSWORD is not set")

    service = GraphitiService(neo4j_password)

    try:
        await service.initialize()

        await service.add_context(
            group_id=group_id,
            content=project_context,
            source_description="Queryable Chatbot complete architecture",
        )

        print("=" * 60)
        print("COMPLETE PROJECT CONTEXT ADDED TO GRAPHITI")
        print("=" * 60)
        print("Group:", group_id)
        print("Components documented:")
        print("- MongoDB")
        print("- Neo4j")
        print("- Graphiti")
        print("- LangChain")
        print("- Jev")
        print("- FastAPI")
        print("- Gemini")
        print("- OpenRouter")
        print("- OpenUI")
        print("=" * 60)

    finally:
        await service.close()


if __name__ == "__main__":
    asyncio.run(main())