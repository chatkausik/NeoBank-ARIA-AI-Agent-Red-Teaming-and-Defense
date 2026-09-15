"""API-key validation and fictional customer identity selection."""

import streamlit as st
import openai
import database


def validate_openai_key(api_key: str):
    """
    Validate the user-supplied OpenAI API key.

    Returns:
        (True, "") if valid
        (False, "error message") if invalid
    """

    if not api_key or not api_key.strip():
        return False, "Please enter your OpenAI API key in the sidebar."

    api_key = api_key.strip()

    # Reject obvious junk before making a network request.
    if len(api_key) < 20:
        return False, "That OpenAI API key does not look valid."

    try:
        client = openai.OpenAI(
            api_key=api_key,
            timeout=10.0,
        )

        # Lightweight authentication check.
        client.models.list()

        return True, ""

    except openai.AuthenticationError:
        return False, "The OpenAI API key is invalid."

    except openai.APIConnectionError:
        return False, (
            "Could not reach OpenAI to verify the API key. "
            "Please check your connection and try again."
        )

    except openai.RateLimitError:
        # The key authenticated, but the account may be rate-limited.
        return True, ""

    except Exception:
        return False, "Could not verify the OpenAI API key. Please try again."


def render_login(conn):
    """Render the login page."""

    st.markdown(
        """
        <div style="text-align:center; margin-top:3rem; margin-bottom:1rem;">
            <h1 style="font-size:32px; font-weight:700; letter-spacing:-0.5px;">
                🏦 NeoBank
            </h1>
            <p style="font-size:14px; color:var(--text-color);">
                Sign in to speak with ARIA, your AI banking assistant
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 1.2, 1])

    with col2:
        with st.form("login_form"):
            name = st.text_input(
                "Full Name",
                placeholder="e.g. Alex Mercer",
            )

            submitted = st.form_submit_button(
                "Sign In",
                use_container_width=True,
            )

            if submitted:

                # ─────────────────────────────
                # 1. Check API key exists
                # ─────────────────────────────

                api_key = st.session_state.get(
                    "api_key",
                    "",
                ).strip()

                if not api_key:
                    st.error(
                        "Please enter your OpenAI API key "
                        "in the sidebar."
                    )
                    return

                # ─────────────────────────────
                # 2. Verify API key with OpenAI
                # ─────────────────────────────

                with st.spinner(
                    "Verifying OpenAI API key..."
                ):
                    key_valid, key_error = (
                        validate_openai_key(api_key)
                    )

                if not key_valid:
                    st.error(key_error)
                    return

                # ─────────────────────────────
                # 3. Check name
                # ─────────────────────────────

                if not name or not name.strip():
                    st.error(
                        "Please enter your name to sign in."
                    )
                    return

                # ─────────────────────────────
                # 4. Authenticate NeoBank user
                # ─────────────────────────────

                customer = database.authenticate_by_name(
                    conn,
                    name.strip(),
                )

                if not customer:
                    st.error(
                        "We couldn't find an account with "
                        "that name. Please check the spelling "
                        "and try again."
                    )
                    return

                # ─────────────────────────────
                # 5. Successful login
                # ─────────────────────────────

                st.session_state.logged_in = True

                st.session_state.user_name = (
                    customer["name"]
                )

                st.session_state.user_id = (
                    customer["user_id"]
                )

                st.session_state.account_tier = (
                    customer["tier"]
                )

                st.session_state.messages = []

                # Remember the exact API key that passed
                # OpenAI validation.
                st.session_state.api_key_validated = (
                    api_key
                )

                st.rerun()

        st.markdown(
            """
            <p style="
                text-align:center;
                font-size:11px;
                color:var(--text-color); opacity:0.65;
                margin-top:1rem;
            ">
                AI Agent Security Demo · NeoBank is fictional
            </p>
            """,
            unsafe_allow_html=True,
        )
