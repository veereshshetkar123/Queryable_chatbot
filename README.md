# Queryable Chatbot

A Queryable Chatbot that allows users to ask questions in natural language and retrieve information from structured business data stored in MongoDB.

The system combines a queryable LangChain agent with Jev routing, Graphiti knowledge/context management, Neo4j, Gemini through OpenRouter, FastAPI, and an OpenUI frontend.

## Architecture

```text
User
  ↓
OpenUI Frontend
  ↓
FastAPI Backend
  ↓
Jev
  ↓
Graphiti Context
  ↓
LangChain Queryable Agent
  ↓
MongoDB
  ↓
Gemini via OpenRouter
  ↓
Response
  ↓
OpenUI
Graphiti uses Neo4j as its graph database for storing contextual knowledge, entities, and relationships.
Technologies Used
Technology
Purpose
OpenUI
Frontend and response presentation
FastAPI
Backend API and request handling
Jev
Request routing and verification
LangChain
Queryable agent and database interaction
MongoDB
Structured business data
Graphiti
Knowledge graph and contextual memory
Neo4j
Graph database used by Graphiti
Gemini
Large language model
OpenRouter
LLM API gateway
Python
Backend development
TypeScript
OpenUI frontend
How It Works
The user enters a question through the OpenUI frontend.
OpenUI sends the request to the FastAPI backend.
FastAPI uses Jev for request routing and verification.
Graphiti provides relevant contextual knowledge when available.
LangChain handles database-related questions.
The queryable agent retrieves structured information from MongoDB.
Gemini is used for language understanding and response generation through OpenRouter.
Graphiti uses Neo4j to store and retrieve contextual relationships.
The final response is returned to OpenUI.
OpenUI presents the response as text, tables, charts, or other structured output.
Component Responsibilities
MongoDB
MongoDB is the source of truth for structured business data.
The queryable agent uses MongoDB to retrieve exact records and perform data-related queries.
LangChain
LangChain is used to build the queryable agent.
It interprets user questions, works with database tools, and retrieves information from MongoDB.
Jev
Jev is used as a backend routing and verification component.
It helps determine the appropriate path for incoming requests, such as database-related requests or general conversation.
Graphiti
Graphiti provides the contextual knowledge and memory layer.
It stores useful project context, entities, relationships, and other information that can be retrieved for relevant queries.
Neo4j
Neo4j is the graph database used by Graphiti.
It stores the graph structures, entities, and relationships required by the Graphiti knowledge layer.
FastAPI
FastAPI provides the backend API.
It connects the frontend request with the routing, contextual knowledge, queryable agent, and database layers.
Gemini and OpenRouter
Gemini is used as the language model.
OpenRouter provides the API gateway through which the application accesses the configured language models.
OpenUI
OpenUI provides the user-facing interface and presentation layer.
It can display normal responses as well as structured outputs such as tables and charts.
Project Structure
queryable_chatbot/
│
├── backend/
│   ├── agent.py
│   ├── answer.py
│   ├── database_tool.py
│   ├── gemini_rest.py
│   ├── graphiti_service.py
│   ├── jev_router.py
│   ├── langchain_agent.py
│   ├── langchain_tools.py
│   ├── llm.py
│   ├── main.py
│   ├── mongodb.py
│   ├── query_executor.py
│   ├── queryable_agent.py
│   ├── schema_discovery.py
│   └── validator.py
│
├── openui_test/
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── next.config.ts
│
├── .gitignore
└── README.md
Backend Flow
POST /ask
    ↓
FastAPI
    ↓
Jev routing
    ↓
Graphiti context
    ↓
LangChain Queryable Agent
    ↓
MongoDB
    ↓
Answer
Graph Knowledge Flow
Project / User Context
        ↓
     Graphiti
        ↓
      Neo4j
        ↓
Entities + Relationships + Context
        ↓
Relevant Context Retrieval
Running the Backend
Create and activate the Python virtual environment:
python -m venv .venv
.\.venv\Scripts\Activate.ps1
Install the required Python dependencies:
pip install -r requirements.txt
Start the FastAPI backend:
uvicorn backend.main:app --reload
The backend will normally be available at:
http://127.0.0.1:8000
Running the OpenUI Frontend
Move into the OpenUI project:
cd openui_test
Install the frontend dependencies:
npm install
Start the development server:
npm run dev
The OpenUI frontend will normally be available at:
http://localhost:3000
Environment Variables
API keys and credentials should be stored in environment variables and must not be committed to GitHub.
Example:
OPENROUTER_API_KEY=your_key_here
Never commit .env files or expose API keys in source code.
Data Sources
The application uses MongoDB for structured business data and Graphiti/Neo4j for contextual knowledge and relationships.
MongoDB remains the source for exact structured business information, while Graphiti and Neo4j provide contextual knowledge.
Current Capabilities
Natural-language questions
MongoDB data retrieval
Queryable LangChain agent
Jev request routing
Graphiti contextual knowledge
Neo4j knowledge graph
Gemini LLM integration
OpenRouter model gateway
FastAPI backend
OpenUI frontend
Table-based responses
Chart-based responses
General conversational questions
Security
Do not commit:
API keys
Passwords
.env files
Database credentials
Private tokens
Other sensitive credentials
These should remain in local environment configuration.
Project Goal
The goal of this project is to provide a natural-language interface for querying structured business data while combining database retrieval with contextual knowledge and an interactive AI-powered user interface.