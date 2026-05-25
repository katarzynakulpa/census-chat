# US Census Chat Agent

An interactive, production-quality chat agent that answers natural language questions about US population and demographics using the US Census Bureau dataset hosted in Snowflake.

## Live Demo

**URL:** _(to be added after deployment)_

No local setup required — the application is deployed on Streamlit Community Cloud.

## Architecture

```
User Question
     │
     ▼
┌─────────────┐
│  Guardrails │  ← input validation, topic check, prompt injection detection
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  GPT-4o     │  ← generates SQL from natural language + schema context
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Snowflake  │  ← executes read-only SQL against Census dataset
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  GPT-4o     │  ← interprets results into natural language
└──────┬──────┘
       │
       ▼
   Chat Response (with optional SQL preview)
```

### Key Components

| Module | Purpose |
|---|---|
| `app.py` | Streamlit chat UI with session state management |
| `agent/chat.py` | Core orchestrator: message → guardrails → LLM → SQL → results → response |
| `agent/database.py` | Snowflake connection, schema discovery, read-only query execution |
| `agent/guardrails.py` | Input validation, topic filtering, prompt injection detection, SQL sanitisation |
| `agent/prompts.py` | Centralised prompt templates for SQL generation and result interpretation |

### Design Decisions

1. **Text-to-SQL approach** — The LLM generates SQL directly from the user's question and the database schema. This grounds responses in real data and prevents hallucination of statistics.

2. **Two-step LLM pipeline** — Step 1: generate SQL. Step 2: interpret results in natural language. This separation makes the system more debuggable and testable.

3. **Hardcoded schema + dynamic discovery fallback** — The system prompt contains the exact column list from the free-tier Census dataset, with clear annotations of which columns are free vs paid-only. Dynamic schema discovery supplements this at startup.

4. **Error recovery with retry** — If a generated SQL query fails, the agent feeds the error back to the LLM for one self-correction attempt before surfacing a user-friendly message.

5. **Streamlit over React** — Chose Streamlit to maximise time on AI engineering and production-quality agent behaviour rather than custom frontend work. Streamlit's built-in chat components provide a clean UX.

## Local Development

### Prerequisites
- Python 3.11+
- Snowflake trial account with US Census dataset from Marketplace
- OpenAI API key

### Setup

```bash
cd census-chat
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt

# Copy and fill in credentials
cp .env.example .env
```

### Explore the dataset

```bash
python -m scripts.explore_schema
```

### Run the app

```bash
streamlit run app.py
```

### Run tests

```bash
pytest tests/ -v
```

## Deployment (Streamlit Community Cloud)

1. Push to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your repo, set `app.py` as the main file
4. Add secrets in the Streamlit Cloud dashboard:

```toml
[snowflake]
account = "..."
user = "..."
password = "..."
warehouse = "COMPUTE_WH"
database = "US_CENSUS_DATA__DEMOGRAPHIC_INSIGHTS__FREE_DATASET"
schema = "DATA_LISTINGS_SCH"

[openai]
api_key = "sk-..."
```

## Configuration

| Variable | Description | Default |
|---|---|---|
| `SNOWFLAKE_ACCOUNT` | Snowflake account identifier | — |
| `SNOWFLAKE_USER` | Username | — |
| `SNOWFLAKE_PASSWORD` | Password | — |
| `SNOWFLAKE_WAREHOUSE` | Compute warehouse | `COMPUTE_WH` |
| `SNOWFLAKE_DATABASE` | Database name | `US_CENSUS_DATA__DEMOGRAPHIC_INSIGHTS__FREE_DATASET` |
| `SNOWFLAKE_SCHEMA` | Schema name | `DATA_LISTINGS_SCH` |
| `OPENAI_API_KEY` | OpenAI API key | — |
