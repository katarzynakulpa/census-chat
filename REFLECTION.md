# Reflection

## Development Process

I approached this in three phases:

1. **Architecture design** (~1h) — Chose a text-to-SQL pipeline with two-step LLM calls (generate SQL, then interpret results). This grounds every response in actual data rather than relying on the LLM's parametric knowledge.

2. **Core implementation** (~3–4h) — Built the agent pipeline, database layer, guardrails, and Streamlit UI. Prioritised the agent logic and error handling over frontend polish.

3. **Testing & deployment** (~1–2h) — Wrote unit tests with mocked dependencies, deployed to Streamlit Community Cloud.

## Key Architectural Decisions

### Text-to-SQL vs. RAG
I chose text-to-SQL over a RAG approach because the data is structured and lives in a SQL database. RAG would require embedding table data into vectors, which adds complexity and loses the precision of SQL aggregations. Text-to-SQL lets the LLM leverage its strong SQL generation capabilities while keeping responses grounded in exact query results.

### Two-step LLM pipeline
Separating SQL generation from result interpretation makes the system:
- **Debuggable** — you can inspect the SQL independently of the answer
- **Testable** — each step can be tested in isolation
- **Transparent** — users can see the SQL that produced their answer

### Explicit schema in system prompt
Rather than relying solely on dynamic discovery, I hardcoded the available column list (with descriptions and free/paid annotations) directly into the system prompt. This gives the LLM precise context about what data is queryable and prevents it from generating SQL against paid-only columns that return "On Suscription" text. Dynamic discovery supplements this as a fallback.

### Model choice: GPT-4o
I chose GPT-4o over cheaper alternatives (GPT-4o-mini, GPT-3.5-turbo) because:
- **SQL generation quality** — Text-to-SQL is the critical path. A wrong query means a wrong answer. GPT-4o produces significantly more accurate SQL than smaller models, especially for aggregations, conditional logic, and multi-column queries.
- **Single table, simple schema** — A cheaper model like GPT-4o-mini could likely handle this specific dataset (one table, straightforward columns). In production with more tables and complex joins, the quality gap would widen. For a demo evaluated by engineers, I prioritised correctness over cost optimisation.
- **Cost is negligible at demo scale** — With 2 evaluators asking maybe 20 questions each, the total cost difference is ~$0.02 vs ~$0.10. Not worth risking incorrect SQL.
- **With more time** I would benchmark GPT-4o-mini on a curated test set of 30+ questions. If accuracy is comparable (>95%), I'd switch to it for production cost savings (~10x cheaper).

### Streamlit
I chose Streamlit over a custom React frontend to maximise time on AI engineering. Streamlit's built-in chat components, session state, and free cloud deployment made it the right trade-off for a 24-hour assignment.

## What I Would Improve With More Time

1. **Schema-aware prompt optimisation** — Currently the full schema is included in every prompt. With more time, I'd implement a schema selection step that only includes relevant tables based on the user's question, reducing token usage and improving accuracy.

2. **Query result caching** — Cache frequent queries (e.g., "total US population") to reduce Snowflake costs and response latency.

3. **Streaming responses** — Use OpenAI streaming to show partial responses as they generate, improving perceived latency.

4. **Better ambiguity handling** — Implement a classification step before SQL generation that detects ambiguous queries and proactively asks clarifying questions (e.g., "Which year?" or "At what geographic level?").

5. **Observability** — Add structured logging, request tracing, and basic analytics (query patterns, error rates, latency percentiles).

6. **Authentication** — Add basic auth or API key protection for the deployed app.

7. **Integration tests** — Test the full pipeline with a real Snowflake connection and known query/answer pairs.

## Edge Cases & Failure Modes

### Identified and handled:
- **Off-topic questions** — Soft keyword filter + LLM system prompt guardrail
- **Prompt injection** — Regex-based detection of common injection patterns
- **SQL injection / DML** — Read-only validation on all generated SQL
- **Query failures** — One retry with LLM error recovery, then graceful error message
- **Empty results** — LLM interprets empty results and suggests refinements
- **Very long inputs** — Character limit enforcement

### Identified but not fully addressed:
- **Ambiguous geographic levels** — "Population of Portland" could mean Portland, OR or Portland, ME. The LLM sometimes guesses rather than asking.
- **Year ambiguity** — When the dataset has multiple years, the agent doesn't always clarify which year the user wants.
- **Single-table limitation** — The free dataset has only one table. The architecture supports multi-table but the demo doesn't showcase it.
- **Rate limiting** — No explicit rate limiting on the API or Snowflake connections.
- **Token budget management** — Very long conversations may exceed the context window; current trimming is basic.

## Testing Strategy

### Current approach:
- **Unit tests** with mocked Snowflake and OpenAI dependencies
- **Guardrail tests** covering input validation, topic filtering, SQL sanitisation, and prompt injection detection
- **Agent flow tests** covering the happy path, error recovery, read-only violations, and edge cases

### What I would add:
- **Integration tests** against a real Snowflake instance with known data
- **LLM output evaluation** — Test that generated SQL is valid and returns expected results for a curated set of questions
- **Load testing** — Verify the 60-second response time requirement under concurrent users
- **Regression tests** — A growing suite of question/answer pairs that verify the agent doesn't regress on previously working queries
