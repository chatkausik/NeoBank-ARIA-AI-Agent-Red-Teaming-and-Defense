"""Shared Streamlit page configuration and styles."""

import streamlit as st


def configure_page():
    st.set_page_config(
        page_title="NeoBank ARIA",
        page_icon="🏦",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    st.markdown("""
    <style>
        .block-container { padding-top: 2rem; }
        .login-title {
            font-size: 24px; font-weight: 700; color: var(--text-color);
            margin-bottom: 4px; letter-spacing: -0.3px;
        }
        .login-sub {
            font-size: 13px; color: var(--text-color); margin-bottom: 1.5rem;
        }
        .hint-card {
            background: rgba(128,128,128,0.06); border: 1px solid rgba(128,128,128,0.18);
            border-radius: 10px; padding: 14px 16px; margin-bottom: 10px;
        }
        .badge-easy {
            display: inline-block; font-size: 10px; font-weight: 700;
            padding: 2px 8px; border-radius: 10px;
            background: #eaf5e0; color: #3a7a10;
        }
        .badge-medium {
            display: inline-block; font-size: 10px; font-weight: 700;
            padding: 2px 8px; border-radius: 10px;
            background: #fef3e0; color: #9a6000;
        }
        .badge-hard {
            display: inline-block; font-size: 10px; font-weight: 700;
            padding: 2px 8px; border-radius: 10px;
            background: #feeaea; color: #a02020;
        }
        .chat-header {
            padding: 12px 0; border-bottom: 1px solid rgba(128,128,128,0.25); margin-bottom: 1rem;
        }
        .chat-header h2 { font-size: 18px; font-weight: 700; color: var(--text-color); margin: 0; }
        .chat-header p { font-size: 12px; color: var(--text-color); margin: 0; }
        .html-frame iframe { width: 100%; border: none; border-radius: 8px; }
    
        /* ── Ensure sidebar inputs remain interactive ── */
        section[data-testid="stSidebar"] div[data-testid="stTextInput"] {
            position: relative !important;
            z-index: 20 !important;
            pointer-events: auto !important;
        }
    
        section[data-testid="stSidebar"] div[data-testid="stTextInput"] > div {
            pointer-events: auto !important;
        }
    
        section[data-testid="stSidebar"] div[data-testid="stTextInput"] input {
            position: relative !important;
            z-index: 21 !important;
            pointer-events: auto !important;
            cursor: text !important;
        }
    
        /* ── Sidebar navigation buttons ── */
    
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button {
            text-align: left;
            justify-content: flex-start;
            font-weight: 600;
            border-radius: 10px;
            padding: 0.55rem 0.85rem;
            transition: background 0.15s ease, border-color 0.15s ease;
        }
    
        /* Text inside all navigation buttons */
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button p {
            text-align: left;
            width: 100%;
            color: var(--text-color) !important;
        }
    
        /* Inactive navigation */
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"] {
            background: transparent;
            border: 1px solid transparent;
            color: var(--text-color) !important;
        }
    
        /* Inactive hover */
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"]:hover {
            background: rgba(128, 128, 128, 0.08);
            border-color: rgba(128, 128, 128, 0.15);
            color: var(--text-color) !important;
        }
    
        /* Active navigation */
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] {
            background: rgba(96, 165, 250, 0.16);
            border: 1px solid rgba(96, 165, 250, 0.45);
            color: var(--text-color) !important;
        }
    
        /* Active hover */
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"]:hover {
            background: rgba(96, 165, 250, 0.24);
            color: var(--text-color) !important;
        }
    </style>
    """, unsafe_allow_html=True)
