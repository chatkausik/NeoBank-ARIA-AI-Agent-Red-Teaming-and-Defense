# app.py — Streamlit entry point for the ARIA security demo.

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from database import get_connection, init_database
from ui.styles import configure_page
from ui.navigation import render_sidebar
from ui.login import render_login
from ui.chat import render_chat
from ui.reports import (
    render_redteam_log, render_findings, render_architecture, render_security_guide,
)

configure_page()


@st.cache_resource
def init_db():
    """Connect to SQLite and seed data (runs once)."""
    conn = get_connection()
    init_database(conn)
    return conn


def main():
    conn = init_db()
    render_sidebar()

    page = st.session_state.get("page", "💬 Chat with ARIA")

    if "Chat" in page:
        if st.session_state.get("logged_in"):
            render_chat(conn)
        else:
            render_login(conn)
    elif "Red Team Log" in page:
        if st.session_state.get("logged_in"):
            render_redteam_log()
        else:
            st.info("Sign in on the Chat page to start capturing evidence.")
    elif "Findings" in page:
        render_findings()
    elif "Architecture" in page:
        render_architecture()
    elif "Security" in page:
        render_security_guide()

if __name__ == "__main__":
    main()
