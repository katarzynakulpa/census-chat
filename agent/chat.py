"""Core chat agent logic.

Orchestrates the flow: user message → guardrails → LLM (SQL generation) →
Snowflake execution → LLM (result interpretation) → response.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import openai

from agent.database import execute_query, discover_schema
from agent.guardrails import validate_input, is_on_topic, sanitize_sql_output
from agent.prompts import SYSTEM_PROMPT, INTERPRET_RESULTS_PROMPT, ERROR_RECOVERY_PROMPT

logger = logging.getLogger(__name__)

MODEL = "gpt-4o"
MAX_CONVERSATION_TURNS = 20  # keep last N turns to manage token usage
MAX_RETRY_ATTEMPTS = 1  # retry once on SQL error


@dataclass
class Message:
    role: str  # "user", "assistant", "system"
    content: str


@dataclass
class AgentResponse:
    """Structured response from the agent."""
    answer: str
    sql_query: str | None = None
    error: str | None = None
    execution_time_ms: int = 0


@dataclass
class ChatSession:
    """Maintains conversation state for a single user session."""
    messages: list[Message] = field(default_factory=list)
    schema_cache: str | None = None

    def add_message(self, role: str, content: str) -> None:
        self.messages.append(Message(role=role, content=content))
        # Trim old messages to stay within context limits
        if len(self.messages) > MAX_CONVERSATION_TURNS * 2:
            self.messages = self.messages[-(MAX_CONVERSATION_TURNS * 2):]

    def get_openai_messages(self, system_prompt: str) -> list[dict[str, str]]:
        msgs = [{"role": "system", "content": system_prompt}]
        for m in self.messages:
            msgs.append({"role": m.role, "content": m.content})
        return msgs


class CensusAgent:
    """Main agent class that handles the full question-answering pipeline."""

    def __init__(self, openai_client: openai.OpenAI, snowflake_conn: Any):
        self.client = openai_client
        self.conn = snowflake_conn
        self._schema_cache: str | None = None

    def get_schema(self) -> str:
        """Get database schema, caching after first call."""
        if self._schema_cache is None:
            logger.info("Discovering database schema...")
            self._schema_cache = discover_schema(self.conn)
            logger.info("Schema cached (%d chars)", len(self._schema_cache))
        return self._schema_cache

    def process_message(self, session: ChatSession, user_message: str) -> AgentResponse:
        """Process a user message and return a response.

        This is the main entry point for the agent.
        """
        start_time = time.time()

        # Step 1: Input validation
        is_valid, rejection = validate_input(user_message)
        if not is_valid:
            return AgentResponse(answer=rejection)

        # Step 2: Topic check (soft filter)
        on_topic, suggestion = is_on_topic(user_message)
        if not on_topic:
            return AgentResponse(answer=suggestion)

        # Step 3: Add user message to session
        session.add_message("user", user_message)

        # Step 4: Get schema
        try:
            schema = self.get_schema()
        except Exception as e:
            logger.error("Failed to discover schema: %s", e)
            return AgentResponse(
                answer="I'm having trouble connecting to the database right now. Please try again in a moment.",
                error=str(e),
            )

        # Step 5: Call LLM to generate SQL or direct response
        system_prompt = SYSTEM_PROMPT.format(schema=schema)
        messages = session.get_openai_messages(system_prompt)

        try:
            llm_response = self._call_llm(messages)
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            return AgentResponse(
                answer="I'm having trouble processing your request right now. Please try again.",
                error=str(e),
            )

        # Step 6: Extract SQL if present
        sql = self._extract_sql(llm_response)

        if sql is None:
            # LLM decided to respond directly (clarification, off-topic decline, etc.)
            session.add_message("assistant", llm_response)
            elapsed = int((time.time() - start_time) * 1000)
            return AgentResponse(answer=llm_response, execution_time_ms=elapsed)

        # Step 7: Sanitize and execute SQL
        sql = sanitize_sql_output(sql)
        result = self._execute_with_retry(session, user_message, sql, schema)

        elapsed = int((time.time() - start_time) * 1000)
        result.execution_time_ms = elapsed
        session.add_message("assistant", result.answer)
        return result

    def _call_llm(self, messages: list[dict[str, str]], temperature: float = 0.1) -> str:
        """Make an OpenAI chat completion call."""
        response = self.client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=2000,
        )
        return response.choices[0].message.content or ""

    def _extract_sql(self, llm_text: str) -> str | None:
        """Extract SQL query from LLM response (looks for ```sql ... ``` blocks)."""
        pattern = r"```sql\s*(.*?)\s*```"
        match = re.search(pattern, llm_text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    def _execute_with_retry(
        self,
        session: ChatSession,
        user_message: str,
        sql: str,
        schema: str,
    ) -> AgentResponse:
        """Execute SQL query, with one retry on failure using LLM error recovery."""
        for attempt in range(1 + MAX_RETRY_ATTEMPTS):
            try:
                result = execute_query(self.conn, sql)
                # Interpret results with LLM
                answer = self._interpret_results(user_message, sql, result)
                return AgentResponse(answer=answer, sql_query=sql)

            except ValueError as e:
                # Read-only violation — don't retry
                return AgentResponse(
                    answer="I can only run read-only queries against the Census database. "
                           "I can't modify any data.",
                    sql_query=sql,
                    error=str(e),
                )

            except RuntimeError as e:
                if attempt < MAX_RETRY_ATTEMPTS:
                    logger.warning("Query failed (attempt %d), trying recovery: %s", attempt + 1, e)
                    recovered = self._recover_from_error(session, user_message, sql, str(e), schema)
                    if recovered:
                        sql = recovered
                        continue
                # Final failure
                return AgentResponse(
                    answer="I wasn't able to retrieve the data for that question. "
                           f"The database returned an error: {e}\n\n"
                           "Could you try rephrasing your question, or ask me what data is available?",
                    sql_query=sql,
                    error=str(e),
                )

        # Should not reach here, but just in case
        return AgentResponse(answer="Something went wrong. Please try again.")

    def _interpret_results(
        self,
        question: str,
        sql: str,
        result: dict[str, Any],
    ) -> str:
        """Use the LLM to turn raw query results into a natural-language answer."""
        truncated_note = " — results truncated" if result["truncated"] else ""

        # Format rows for the prompt
        rows_text = ""
        for row in result["rows"][:50]:  # limit what we send to the LLM
            rows_text += str(row) + "\n"

        if not result["rows"]:
            rows_text = "(no rows returned)"

        prompt = INTERPRET_RESULTS_PROMPT.format(
            question=question,
            sql=sql,
            row_count=result["row_count"],
            truncated_note=truncated_note,
            columns=result["columns"],
            rows_text=rows_text,
        )

        messages = [
            {"role": "system", "content": "You are a helpful data analyst. Present query results clearly."},
            {"role": "user", "content": prompt},
        ]
        return self._call_llm(messages, temperature=0.2)

    def _recover_from_error(
        self,
        session: ChatSession,
        question: str,
        sql: str,
        error: str,
        schema: str,
    ) -> str | None:
        """Ask the LLM to fix a failed SQL query. Returns corrected SQL or None."""
        prompt = ERROR_RECOVERY_PROMPT.format(question=question, sql=sql, error=error)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT.format(schema=schema)},
            {"role": "user", "content": prompt},
        ]
        try:
            recovery_response = self._call_llm(messages)
            return self._extract_sql(recovery_response)
        except Exception as e:
            logger.error("Error recovery LLM call failed: %s", e)
            return None
