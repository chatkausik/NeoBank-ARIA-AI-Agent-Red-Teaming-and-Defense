"""Experiment session state, independent of individual views."""

import streamlit as st
from defenses import conversation_guard as cguard


def _reset_chat_for_configuration():
    """Start a fresh experiment when its mode or model changes."""
    if st.session_state.get("messages"):
        st.session_state.run_notice = (
            "Started a fresh conversation for this configuration. "
            "Previous turns remain in the Red Team Log."
        )
    st.session_state.messages = []
    st.session_state.guard_state = cguard.new_state()
