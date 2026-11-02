# Queryable Chatbot

Ask questions about your business data in plain English and get answers, tables and charts, without writing a single database query.

> "How many companies are in India?" · "Which deployment type has the highest average HR tech spend?" · "Show attrition by department"

The chatbot turns each question into a **validated, read-only MongoDB query**, runs it, and replies with a rich answer rendered by **OpenUI** (tables, charts, cards). API keys stay on the server; the browser never sees them.

---

## Features

- **Natural-language → MongoDB:** `find`, `count`, `distinct` and `aggregate` queries are generated from the live database schema.
- **Safe by design:** every generated query is validated (collections, fields, operators, allowed aggregation stages, time and row limits). Write operations are rejected, and PII is redacted.
- **Smart routing:** Jev (via OpenRouter) decides whether a question needs the database; a LangChain classifier is the fallback.
- **Rich answers:** streamed OpenUI components, with a query inspector that shows the exact query that ran.
- **Built-in tools:** insights dashboard, analytics lab, geo explorer, data catalog, usage stats, and voice input.
- **Artifacts library:** every chart, map, insight set and query an answer produces is saved. Browse and search them from **Artifacts** in the sidebar (Charts & insights · Maps · Queries), or open the current chat's artifacts from the workspace rail on the right.
- **Admin console:** for `admin` users, a sidebar **Admin console** with workspace KPIs and 14-day activity, user management (add users, change role/plan, disable, reset password, sign out), feedback review, an audit log of admin actions, and service health.
- **Accounts:** login and sign-up, saved conversations, plans with daily limits, and personal API keys (`qc-...`).
- **Feedback:** 👍 / 👎 on every answer, stored with the query and trace ID for debugging.
- **Production basics:** Docker Compose, health probes, request logs, GitHub Actions CI.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, React 19, TypeScript, OpenUI, D3, three.js (`openui_test/`) |
| Backend | Python 3.10, FastAPI, LangChain (`backend/`) |
| LLM | Gemini 2.5 Flash via **OpenRouter** (configurable) |
| Routing | Jev (OpenRouter decisions API) |
| Database | MongoDB 7 |
| Optional | Graphiti + Neo4j knowledge graph, Langfuse tracing, Thesys OpenUI gateway |

## How it works

```text
Browser ──► Next.js (localhost:3000) ──/api/* proxy──► FastAPI (127.0.0.1:8000)
                                                         │
             1. Guardrails      size, prompt-injection and write-intent checks
             2. Jev routing     database question or general chat?
             3. LangChain       generate a MongoDB query from the discovered schema
             4. Validator       allowlist collections / fields / operators
             5. MongoDB         run it read-only, with timeout and row limit
             6. OpenUI          stream the answer as UI components
```

See [`docs/architecture.md`](docs/architecture.md) for the full endpoint list and request flow.

---

## Quick start (local)

### 1. Prerequisites

- **Python 3.10+**
- **Node.js 20+** and npm
- **MongoDB 7** running on `localhost:27017` ([download](https://www.mongodb.com/try/download/community)), or use Docker (below)
- An **OpenRouter API key**: free sign-up at <https://openrouter.ai/keys>

### 2. Clone and configure

```bash
git clone https://github.com/Veeresh-champ/Queryable-chatbot.git
cd Queryable-chatbot
cp .env.example .env          # Windows PowerShell: copy .env.example .env
```

Open `.env` and set your key; everything else has working defaults:

```dotenv
OPENROUTER_API_KEY=sk-or-v1-...
```

> 🔒 `.env` is git-ignored. Never commit real keys.

### 3. Install the backend

```bash
python -m venv .venv
# Windows:      .\.venv\Scripts\Activate.ps1
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements-dev.txt
```

### 4. Load the sample data into MongoDB

```bash
python -m scripts.import_span_companies     # 500 companies         -> span_companies
python -m scripts.import_ibm_hr             # 1,470 employees       -> ibm_hr_employees
python -m scripts.import_kaggle_ecommerce   # customers, orders ... -> 5 collections
```

Each script replaces its collections, so it is safe to run again.

### 5. Run the app

**Terminal 1: backend**

```bash
uvicorn backend.main:app --reload
```

**Terminal 2: frontend**

```bash
cd openui_test
npm install
npm run dev
```

Open **<http://localhost:3000>**, click **Create account**, and start asking questions.

> **Windows shortcut:** `powershell -ExecutionPolicy Bypass -File start.ps1` starts MongoDB, the backend and the frontend, then opens the browser. If MongoDB will not start, run `scripts\start-mongodb.ps1` once as administrator.

To create a user from the command line instead (for example an admin):

```bash
python -m scripts.create_user admin --role admin
```

Admins see **Admin console** in the sidebar, where they can add more users. To fill the Artifacts library from conversations saved before it existed, run `python -m scripts.backfill_artifacts` once (`--dry-run` shows what it would add).

---

## Run with Docker

```bash
cp .env.example .env              # set OPENROUTER_API_KEY
docker compose up --build -d      # MongoDB + backend + frontend
```

Load the sample data from your machine (MongoDB is published on `127.0.0.1:27017`; set `MONGO_PORT` in `.env` if that port is taken):

```bash
pip install -r requirements-dev.txt
python -m scripts.import_span_companies
python -m scripts.import_ibm_hr
python -m scripts.import_kaggle_ecommerce
```

Then open <http://localhost:3000>. To create an admin user inside the container:

```bash
docker compose exec backend python -m scripts.create_user admin --role admin
```

For production, set `COOKIE_SECURE=true` and `ALLOW_SIGNUP=false`, put HTTPS in front, and give the app a MongoDB user that can only read the business collections.

---

## Deploy (Cloudflare + Render + MongoDB Atlas)

| Part | Where | Config |
|---|---|---|
| Database | MongoDB Atlas (free M0) | connection string → `MONGODB_URI` |
| Backend (FastAPI) | Render (free, Docker) | [`render.yaml`](render.yaml) |
| Frontend (Next.js) | Cloudflare Workers via OpenNext | [`openui_test/wrangler.jsonc`](openui_test/wrangler.jsonc) |

1. **Atlas:** create a free cluster, a database user, and allow network access from `0.0.0.0/0`. Load the data from your machine:
   ```bash
   MONGODB_URI="mongodb+srv://..." python -m scripts.import_span_companies   # same for import_ibm_hr, import_kaggle_ecommerce
   MONGODB_URI="mongodb+srv://..." python -m scripts.create_user admin --role admin
   ```
2. **Render:** Dashboard → New → Blueprint → pick this repo. Fill in `MONGODB_URI`, `OPENROUTER_API_KEY` and `FRONTEND_URL` (the Cloudflare URL from step 3; update it after the first deploy).
3. **Cloudflare (Git builds):** connect this repo to a Worker named `queryable-chatbot` with Root directory `/`, no build command, and deploy command `npx wrangler deploy`. The root [`wrangler.jsonc`](wrangler.jsonc) builds `openui_test/` with OpenNext and deploys it. The `/api/*` rewrite is fixed at build time, so add a build variable `BACKEND_URL` set to your Render URL (it defaults to `https://queryable-chatbot-api.onrender.com`).

   **Or deploy from your machine:**
   ```bash
   cd openui_test
   npx wrangler login
   BACKEND_URL=https://queryable-chatbot-api.onrender.com npm run cf:deploy
   ```

The free Render service sleeps after ~15 minutes idle; the first request afterwards takes 30–60 s.

---

## Sample datasets

| Collection | Rows | Source |
|---|---:|---|
| `span_companies` | 500 | Synthetic company / HR-tech spend data (`data/span_companies.csv`) |
| `ibm_hr_employees` | 1,470 | [IBM HR Analytics Attrition (Kaggle)](https://www.kaggle.com/datasets/pavansubhasht/ibm-hr-analytics-attrition-dataset) |
| `customers`, `orders`, `order_items`, `products`, `sales_cleaned` | 50–2,000 each | Kaggle e-commerce sample (`data/kaggle_ecommerce/`) |

**Using your own data:** load any collection into the same database and the chatbot discovers its schema automatically. To restrict what it may query, set `QUERYABLE_COLLECTIONS=coll_a,coll_b` in `.env`.

### Example questions

- How many companies are in India?
- Which country has the highest total HR tech spend?
- Average spend by deployment type
- What is the attrition rate by department?
- Top 5 products by revenue

---

## Configuration

All settings live in `.env` and are documented in [`.env.example`](.env.example). The ones you are most likely to change:

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | — | **Required.** Used for routing, query generation and answers |
| `MONGODB_URI` | `mongodb://localhost:27017` | MongoDB connection |
| `MONGODB_DB` | `queryable_chatbot` | Database name |
| `AGENT_MODEL` / `OPENUI_MODEL` | `google/gemini-2.5-flash` | Any OpenRouter model ID |
| `QUERYABLE_COLLECTIONS` | *(all)* | Allowlist of collections the bot may read |
| `JEV_ENABLED` | `true` | Use Jev for routing (falls back to LangChain) |
| `ALLOW_SIGNUP` | `true` | Show self-service sign-up |
| `GRAPHITI_ENABLED` | `false` | Add Graphiti/Neo4j context (needs Neo4j + `pip install graphiti-core neo4j`) |
| `LANGFUSE_*` | — | Optional tracing |

The frontend needs no keys. `openui_test/.env.example` only sets `BACKEND_URL`, which defaults to `http://127.0.0.1:8000`.

---

## API

The interactive docs are at **<http://127.0.0.1:8000/docs>** while the backend runs. Main endpoints:

| Endpoint | Purpose |
|---|---|
| `POST /api/chat` | Streaming chat (AG-UI / SSE), used by the UI |
| `POST /ask` | Simple JSON question → answer |
| `/api/auth/*` | Login, logout, sign-up, current user |
| `/api/threads/*` | Saved conversations |
| `/api/account/*` | Plan, usage, personal API keys |
| `/api/feedback/*` | Answer ratings |
| `/api/artifacts/*` | Saved artifacts (list, search, open, rename, delete) |
| `/api/admin/*` | Admin console: overview, users, audit log (admins only) |
| `/api/insights/overview`, `/api/analytics/lab`, `/api/geo/*`, `/api/catalog` | Dashboard tools |
| `/api/livez`, `/api/readyz`, `/api/health` | Health probes |

You can call the API with a personal key from **Settings → API keys**:

```bash
curl http://127.0.0.1:8000/ask \
  -H "Authorization: Bearer qc-..." \
  -H "Content-Type: application/json" \
  -d '{"question": "How many companies are in India?"}'
```

---

## Testing

```bash
python -m pytest                  # backend: 135 tests, needs MongoDB running
cd openui_test
npm run typecheck && npm run lint # frontend
```

The tests use a separate `queryable_chatbot_test` database and mock every LLM call, so they need **no API key** and never touch your data. Tests marked `live` (real OpenRouter calls) are skipped by default; run them with `python -m pytest -m live`.

`python evaluate_golden_set.py` runs a small golden-question set against the real model and writes `evaluation_results.json`.

GitHub Actions (`.github/workflows/ci.yml`) runs the backend tests, the frontend typecheck, lint and build, and both Docker image builds on every push.

---

## Project structure

```text
Queryable-chatbot/
├── backend/                 FastAPI app
│   ├── main.py              app entry point and routes
│   ├── chat_service.py      /api/chat streaming flow
│   ├── langchain_agent.py   routing + query generation
│   ├── jev_router.py        Jev routing
│   ├── schema_discovery.py  reads collection schemas
│   ├── validator.py         query safety checks
│   ├── database_tool.py     runs validated queries
│   ├── guardrails.py        input checks, PII redaction
│   ├── openui_engine.py     OpenUI answer generation
│   ├── auth.py, account.py, threads.py, feedback.py
│   ├── artifacts.py         saved charts/maps/queries (Artifacts library)
│   ├── admin.py             admin console API
│   ├── insights.py, analytics.py, hr_analytics.py, geo.py
│   └── openui/              OpenUI component library + system prompt
├── openui_test/             Next.js frontend
│   ├── src/app/             pages (chat, login, signup)
│   ├── src/components/      chat UI, charts, tools, globe
│   └── scripts/             OpenUI validator (also used by the backend)
├── scripts/                 data importers, create_user, benchmarks
├── tests/                   pytest suite
├── data/                    sample CSV datasets
├── docs/architecture.md
├── Dockerfile, docker-compose.yml
├── requirements.txt, requirements-dev.txt
├── start.ps1                Windows one-command launcher
└── .env.example
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "MongoDB is not reachable" | Start MongoDB (`net start MongoDB` on Windows, or `docker compose up -d mongo`) |
| Answer says "Check OPENROUTER_API_KEY", or `/api/readyz` returns 503 | Set `OPENROUTER_API_KEY` in `.env` and restart the backend |
| The bot says there is no data | Run the three `scripts.import_*` commands |
| Frontend shows network errors | Make sure the backend is running on `127.0.0.1:8000` |
| Port 27017 already in use (Docker) | Set `MONGO_PORT=27018` in `.env` |
