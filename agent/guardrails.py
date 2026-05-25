"""Input and output guardrails for the census chat agent.

Prevents off-topic, inappropriate, or dangerous interactions.
"""

import re

# Topics the agent CAN answer
ALLOWED_TOPICS = [
    "population", "census", "demographic", "age", "race", "ethnicity",
    "gender", "sex", "income", "poverty", "housing", "education",
    "employment", "occupation", "migration", "birth", "death", "fertility",
    "household", "family", "marital", "veteran", "disability", "insurance",
    "commut", "transport", "language", "citizen", "foreign-born",
    "state", "county", "zip", "city", "metropolitan", "rural", "urban",
    "american community survey", "acs", "decennial",
    "us ", "united states", "america",
]

# Patterns that should be rejected outright
BLOCKED_PATTERNS = [
    r"(?i)(ignore|forget|disregard)\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)",
    r"(?i)you\s+are\s+now\s+",
    r"(?i)act\s+as\s+(if\s+you\s+are\s+)?a?\s*(different|new)\s+",
    r"(?i)(jailbreak|DAN|do anything now)",
    r"(?i)(system\s*prompt|reveal\s*(your)?\s*instructions?)",
]

MAX_INPUT_LENGTH = 2000


def validate_input(user_message: str) -> tuple[bool, str]:
    """Validate user input. Returns (is_valid, rejection_reason)."""
    if not user_message or not user_message.strip():
        return False, "I'm all ears, but you haven't typed anything yet. Hit me with a census question!"

    if len(user_message) > MAX_INPUT_LENGTH:
        return False, (
            f"Your message is too long ({len(user_message)} characters). "
            f"Please keep it under {MAX_INPUT_LENGTH} characters."
        )

    # Check for prompt injection attempts
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, user_message):
            return False, (
                "Nice try! 😏 I'm laser-focused on US Census data though. "
                "No jailbreaks, just ZIP codes."
            )

    return True, ""


def is_on_topic(user_message: str) -> tuple[bool, str]:
    """Lightweight check whether the message is plausibly related to census data.

    This is a *soft* filter — the LLM system prompt is the primary guardrail.
    This catches obviously off-topic questions early to save LLM calls.

    Returns (is_on_topic, suggestion).
    """
    msg_lower = user_message.lower()

    # Very short messages (< 3 words) are likely greetings or follow-ups — allow them
    if len(msg_lower.split()) < 3:
        return True, ""

    # Check if any census-related keyword appears
    for topic in ALLOWED_TOPICS:
        if topic in msg_lower:
            return True, ""

    # Also allow questions that reference prior context
    context_references = ["it", "that", "those", "this", "them", "same", "previous", "above", "before", "compare"]
    for ref in context_references:
        if ref in msg_lower.split():
            return True, ""

    # Allow question words that might be census-related
    if any(msg_lower.startswith(w) for w in ["how many", "what is the", "what are", "which", "where", "compare"]):
        return True, ""

    return False, (
        "That's a bit outside my wheelhouse — I'm a one-trick pony, but it's a pretty good trick. "
        "I know population, income, housing, employment, and all things US Census. "
        "Try asking me something demographic-y!"
    )


def sanitize_sql_output(sql: str) -> str:
    """Strip any dangerous statements that might have slipped through the LLM output."""
    lines = sql.strip().split("\n")
    safe_lines = []
    forbidden_starts = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "MERGE", "GRANT", "REVOKE")
    for line in lines:
        stripped = line.strip().upper()
        if any(stripped.startswith(kw) for kw in forbidden_starts):
            continue
        safe_lines.append(line)
    return "\n".join(safe_lines)
