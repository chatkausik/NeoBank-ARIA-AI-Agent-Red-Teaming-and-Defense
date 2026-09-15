# defenses/tool_policy.py — the real security boundary: authorization in code.
#
# Attack families: PII EXTRACTION, CRESCENDO, SOCIAL ENGINEERING.
# Fixes V1: query_account had no ownership check, so any user_id the model
# could be talked into passing returned that customer's full record.
#
# The key idea from the assignment: guardrails are not a substitute for backend
# authorization. Here the tool IGNORES any user_id the model supplies and always
# reads the SESSION user's own account. No prompt trick can change the session
# identity, so no amount of conversation reaches another customer's data.

import logging

from langchain_core.tools import tool

from database import get_customer, get_transactions, format_account_details
from defenses.kb_filter import safe_lookup_policy
from defenses.output_rails import spotlight

logger = logging.getLogger("guarded_aria.tools")


def build_secure_tools(conn, session_user_id: str):
    """Tools for guarded ARIA. Both wrap their output in spotlight delimiters
    so the model treats tool results as data, never as instructions (V5)."""

    @tool
    def lookup_policy(topic: str) -> str:
        """Look up a NeoBank customer policy using one of these canonical keys:
        transfer_limits, dispute_process, card_management, fraud_detection,
        account_verification. Use transfer_limits for wire timing and
        card_management for replacement-card fees."""
        logger.info("[SECURE TOOL] lookup_policy")
        return spotlight(safe_lookup_policy(topic))

    @tool(response_format="content_and_artifact")
    def query_account(user_id: str = "") -> tuple[str, dict]:
        """Look up the signed-in customer's own account details and recent
        transactions. The account is determined by the authenticated session."""
        # Authorization: the model's user_id argument is advisory only. We
        # always serve the session user. If a different id was requested, log
        # it as an attempted cross-account access and still serve only self.
        requested = (user_id or "").strip()
        denied = bool(requested and requested != session_user_id)
        if denied:
            logger.warning("[SECURE TOOL] foreign account request denied; serving session")
        # Metadata comes from the same backend closure that chooses the query
        # identity. It is an artifact for execution evidence, not model content.
        metadata = {"requested_user_id": requested or None,
                    "effective_user_id": session_user_id,
                    "authorization": "denied" if denied else "allowed"}
        customer = get_customer(conn, session_user_id)
        if not customer:
            return spotlight("Account not found for the signed-in user."), metadata
        transactions = get_transactions(conn, session_user_id)
        return spotlight(format_account_details(customer, transactions)), metadata

    return [lookup_policy, query_account]
