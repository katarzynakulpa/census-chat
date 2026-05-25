"""Streamlit chat interface for the US Census data agent."""

import os
import logging

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import openai

from agent.chat import CensusAgent, ChatSession
from agent.database import get_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Census Whisperer",
    page_icon="🧮",
    layout="centered",
)


# ── Initialisation ──────────────────────────────────────────────────────────

def init_openai_client() -> openai.OpenAI:
    """Create OpenAI client from secrets or env vars."""
    try:
        api_key = st.secrets.get("openai", {}).get("api_key", "")
    except Exception:
        api_key = ""
    api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
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

st.title("🧮 Census Whisperer")
st.caption("I've read 33,000 ZIP codes so you don't have to. Ask me anything about US demographics.")

# Sidebar — info & controls
with st.sidebar:
    st.markdown("### About")
    st.markdown(
        "A natural-language agent that queries **33k+ ZIP codes** of US Census data "
        "in Snowflake — so you can skip the SQL and go straight to the insights. "
        "Built with GPT-4o, Snowflake, and an unreasonable fondness for demographics."
    )
    st.markdown("---")
    st.markdown("**Things you can ask me:**")
    st.markdown(
        "- What's the total US population in 2025?\n"
        "- Which state has the richest households?\n"
        "- Texas vs California — who's growing faster?\n"
        "- Where in America is unemployment the worst?\n"
        "- How many housing units does NYC actually have?"
    )
    st.markdown("---")
    if st.button("🧹 Start fresh"):
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
if prompt := st.chat_input("Ask me about population, income, housing… anything census-y"):
    # Show user message
    st.session_state.ui_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Process
    with st.chat_message("assistant"):
        with st.spinner("Crunching census numbers…"):
            try:
                client = init_openai_client()
                sf_conn = init_snowflake()
                agent = init_agent(client, sf_conn)
                response = agent.process_message(st.session_state.chat_session, prompt)
            except Exception as e:
                logger.exception("Unhandled error in agent pipeline")
                response_text = (
                    "Well, that wasn't supposed to happen. 🫠 "
                    "Something broke on my end — try again or rephrase your question."
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
