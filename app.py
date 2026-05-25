"""Streamlit chat interface for the US Census data agent."""

import os
import logging

import streamlit as st
import openai

from agent.chat import CensusAgent, ChatSession
from agent.database import get_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="US Census Chat Agent",
    page_icon="📊",
    layout="centered",
)


# ── Initialisation ──────────────────────────────────────────────────────────

def init_openai_client() -> openai.OpenAI:
    """Create OpenAI client from secrets or env vars."""
    api_key = st.secrets.get("openai", {}).get("api_key", "") or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        st.error("⚠️ OpenAI API key is not configured. Add it to `.streamlit/secrets.toml` or set `OPENAI_API_KEY`.")
        st.stop()
    return openai.OpenAI(api_key=api_key)


@st.cache_resource(show_spinner="Connecting to Snowflake…")
def init_snowflake():
    """Create and cache Snowflake connection."""
    return get_connection()


@st.cache_resource(show_spinner="Initialising agent…")
def init_agent(_openai_client, _sf_conn):
    """Create and cache the CensusAgent (underscore prefix avoids hashing)."""
    agent = CensusAgent(_openai_client, _sf_conn)
    agent.get_schema()  # warm the schema cache
    return agent


# ── Session state ───────────────────────────────────────────────────────────

if "chat_session" not in st.session_state:
    st.session_state.chat_session = ChatSession()

if "ui_messages" not in st.session_state:
    st.session_state.ui_messages = []


# ── UI ──────────────────────────────────────────────────────────────────────

st.title("📊 US Census Chat Agent")
st.caption("Ask me anything about US population, demographics, income, housing, education, and more.")

# Sidebar — info & controls
with st.sidebar:
    st.markdown("### About")
    st.markdown(
        "This agent queries the **US Census Bureau** dataset hosted in Snowflake "
        "to answer your questions using natural language."
    )
    st.markdown("---")
    st.markdown("**Example questions:**")
    st.markdown(
        "- What is the total US population?\n"
        "- Which state has the highest median household income?\n"
        "- Compare population growth in Texas vs California\n"
        "- What percentage of the population has a bachelor's degree?"
    )
    st.markdown("---")
    if st.button("🗑️ Clear conversation"):
        st.session_state.chat_session = ChatSession()
        st.session_state.ui_messages = []
        st.rerun()


# Render chat history
for msg in st.session_state.ui_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sql"):
            with st.expander("🔍 SQL query"):
                st.code(msg["sql"], language="sql")


# Chat input
if prompt := st.chat_input("Ask a question about US Census data…"):
    # Show user message
    st.session_state.ui_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Process
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                client = init_openai_client()
                sf_conn = init_snowflake()
                agent = init_agent(client, sf_conn)
                response = agent.process_message(st.session_state.chat_session, prompt)
            except Exception as e:
                logger.exception("Unhandled error in agent pipeline")
                response_text = (
                    "I'm sorry, something went wrong while processing your request. "
                    "Please try again or rephrase your question."
                )
                st.session_state.ui_messages.append({"role": "assistant", "content": response_text})
                st.markdown(response_text)
                st.stop()

        st.markdown(response.answer)
        if response.sql_query:
            with st.expander("🔍 SQL query"):
                st.code(response.sql_query, language="sql")

    ui_msg: dict = {"role": "assistant", "content": response.answer}
    if response.sql_query:
        ui_msg["sql"] = response.sql_query
    st.session_state.ui_messages.append(ui_msg)
