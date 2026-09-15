"""Manual evidence exports and generated findings/reference views."""

import base64
import csv
import datetime as dt
import io
import json
import os
import re
import streamlit as st

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


RT_LOG_PATH = os.path.join(
    PROJECT_ROOT, "redteam", "results", "manual_log.jsonl"
)


ATTACK_FAMILIES = [
    "(untagged)", "jailbreak", "obfuscation", "sensitive_data_exposure",
    "prompt_injection", "red_team_recon", "crescendo", "pii_extraction",
    "social_engineering", "benign",
]


def _log_turn(prompt, response, mode, model, guard_trace, *,
              tool_trace=None, execution_status="ok", error=None):
    """Append a chat turn to the in-session red-team log (and a local JSONL).

    Store experimental messages, execution state and backend trace metadata.
    Configuration credentials are not added to the evidence.
    """
    entry = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "mode": mode,
        "model": model,
        "prompt": prompt,
        "response": response,
        "trace": [f"{t['layer']}:{t['action']}" for t in guard_trace],
        "tool_trace": tool_trace or [],
        "execution_status": execution_status,
        "error": error,
        "family": "(untagged)",
        "score": "(unscored)",
        "notes": "",
    }
    st.session_state.rt_log.append(entry)
    try:
        os.makedirs(os.path.dirname(RT_LOG_PATH), exist_ok=True)
        with open(RT_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # logging is best-effort; never break the chat


def _rt_log_to_markdown(rows):
    lines = ["# ARIA Red-Team Evidence Log", ""]
    for i, r in enumerate(rows, 1):
        lines += [
            f"## {i}. {r['family']} — {r['score']}  ({r['mode']}, {r['model']})",
            f"- **When:** {r['ts']}",
            f"- **Prompt:** {r['prompt']}",
            f"- **Response:** {r['response']}",
            f"- **Guard trace:** {', '.join(r['trace']) or 'none'}",
            f"- **Execution:** {r.get('execution_status', 'not recorded')}",
            f"- **Notes:** {r['notes']}",
            "",
        ]
    return "\n".join(lines)


def _rt_log_to_csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ts", "family", "score", "mode", "model", "prompt",
                "response", "trace", "notes", "execution_status", "error", "tool_trace"])
    for r in rows:
        w.writerow([r["ts"], r["family"], r["score"], r["mode"], r["model"],
                    r["prompt"], r["response"], "; ".join(r["trace"]), r["notes"],
                    r.get("execution_status", ""), r.get("error", ""),
                    json.dumps(r.get("tool_trace", []), ensure_ascii=False)])
    return buf.getvalue()


def render_redteam_log():
    """Evidence-capture page: every chat turn, taggable and exportable."""
    st.markdown("## 🧪 Red Team Log")
    st.caption(
        "Every chat turn is captured here automatically. Tag each one with an "
        "attack family and a PASS / WARN / FAIL score, then export for your "
        "findings doc. The configured API key is not added to the log; "
        "review message content before sharing."
    )

    rows = st.session_state.get("rt_log", [])
    if not rows:
        st.info("No turns yet. Chat with ARIA (any mode) and they'll appear here.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Turns logged", len(rows))
    c2.metric("FAIL", sum(1 for r in rows if r["score"] == "FAIL"))
    c3.metric("Guarded turns", sum(1 for r in rows if r["mode"] == "Guarded"))

    st.divider()

    for i, r in enumerate(rows):
        header = f"{i+1}. [{r['mode']}] {r['prompt'][:60]}"
        with st.expander(header, expanded=False):
            st.markdown(f"**Prompt:** {r['prompt']}")
            st.markdown(f"**Response:** {r['response']}")
            st.caption(f"{r['ts']} · {r['model']} · trace: "
                       f"{', '.join(r['trace']) or 'none'}")
            if r.get("execution_status") == "error":
                st.error(f"Execution failed: {r.get('error') or 'request_failed'}")
            if r.get("tool_trace"):
                st.json(r["tool_trace"], expanded=False)
            fcol, scol = st.columns(2)
            r["family"] = fcol.selectbox(
                "Attack family", ATTACK_FAMILIES,
                index=ATTACK_FAMILIES.index(r["family"])
                if r["family"] in ATTACK_FAMILIES else 0,
                key=f"fam_{i}")
            r["score"] = scol.selectbox(
                "Score", ["(unscored)", "PASS", "WARN", "FAIL"],
                index=["(unscored)", "PASS", "WARN", "FAIL"].index(r["score"])
                if r["score"] in ["(unscored)", "PASS", "WARN", "FAIL"] else 0,
                key=f"score_{i}")
            r["notes"] = st.text_input("Notes", value=r["notes"], key=f"notes_{i}")

    st.divider()
    dcol1, dcol2, dcol3 = st.columns(3)
    dcol1.download_button(
        "⬇️ Export Markdown", _rt_log_to_markdown(rows),
        file_name="aria_redteam_log.md", use_container_width=True)
    dcol2.download_button(
        "⬇️ Export CSV", _rt_log_to_csv(rows),
        file_name="aria_redteam_log.csv", mime="text/csv",
        use_container_width=True)
    if dcol3.button("🗑️ Clear log", use_container_width=True):
        st.session_state.rt_log = []
        st.rerun()


SECURITY_GUIDE_DARK_CSS = """
<style>
  :root {
    --bg: #0e1117 !important;
    --bg-secondary: #161b22 !important;
    --text: #e6e6e6 !important;
    --text-secondary: #a0a0a0 !important;
    --text-tertiary: #707070 !important;
    --border: rgba(255,255,255,0.12) !important;
    --border-strong: rgba(255,255,255,0.22) !important;
    --red-bg: #2a1515 !important;    --red-border: rgba(255,100,100,0.3) !important;   --red-text: #ff8a8a !important;
    --green-bg: #152215 !important;  --green-border: rgba(100,220,100,0.3) !important; --green-text: #7cd07c !important;
    --amber-bg: #2a2210 !important;  --amber-border: rgba(255,200,100,0.3) !important; --amber-text: #ffc878 !important;
    --blue-bg: #151e2a !important;   --blue-border: rgba(100,160,255,0.3) !important;  --blue-text: #78b4ff !important;
    --purple-bg: #1e1530 !important; --purple-border: rgba(160,120,255,0.3) !important; --purple-text: #b49cff !important;
    --teal-bg: #152a22 !important;   --teal-border: rgba(100,255,200,0.3) !important;  --teal-text: #78ffc8 !important;
  }
  body { background: #0e1117 !important; }
  .cont { background: #161b22 !important; }
  .nav button {
    background: #1c2333 !important; color: #a0a0a0 !important;
    border-color: rgba(255,255,255,0.15) !important;
  }
  .nav button:hover:not(.active) { background: #262d40 !important; }
  .nav button.active {
    background: #1b3a5c !important; color: #78b4ff !important;
    border-color: rgba(100,160,255,0.4) !important;
  }
  code, pre { background: #1a1f2e !important; color: #c8d0e0 !important; }
  table { border-color: rgba(255,255,255,0.15) !important; }
  th { background: #1c2333 !important; color: #a0a0a0 !important; }
  td { border-color: rgba(255,255,255,0.1) !important; }
  input, select, textarea {
    background: #1a1f2e !important; color: #e0e0e0 !important;
    border-color: rgba(255,255,255,0.2) !important;
  }
  .abtn { background: #1b3a5c !important; color: #78b4ff !important; border-color: rgba(100,160,255,0.3) !important; }
  ::-webkit-scrollbar { width: 8px; }
  ::-webkit-scrollbar-track { background: #0e1117; }
  ::-webkit-scrollbar-thumb { background: #333; border-radius: 4px; }
</style>
"""


def _apply_guide_dark_mode(html: str) -> str:
    """Apply dark mode to security_guide.html via CSS variable override."""
    if "</head>" in html:
        html = html.replace("</head>", SECURITY_GUIDE_DARK_CSS + "</head>")
    else:
        html = SECURITY_GUIDE_DARK_CSS + html
    return html


def _render_as_iframe(html_content: str, height: int = 800, allow_print: bool = False):
    """Render HTML as a data-URI iframe."""
    b64 = base64.b64encode(html_content.encode("utf-8")).decode("utf-8")
    sandbox = "allow-scripts allow-same-origin" + (" allow-modals" if allow_print else "")
    st.markdown(
        f'<div class="html-frame">'
        f'<iframe src="data:text/html;base64,{b64}" '
        f'title="ARIA reference document" '
        f'height="{height}" style="width:100%;border:none;border-radius:8px;" '
        f'sandbox="{sandbox}"></iframe>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_findings():
    """Browse generated evidence and the separate source-code review offline."""
    st.markdown("## 📊 Findings Report")
    st.caption("Compare recorded test outcomes, inspect evidence, and review the improvement priorities.")
    docs_dir = os.path.join(PROJECT_ROOT, "docs")
    results_tab, review_tab = st.tabs(["Test results", "Code review"])
    with results_tab:
        html_path = os.path.join(docs_dir, "findings_report.html")
        md_path = os.path.join(docs_dir, "findings_report.md")
        if os.path.exists(html_path):
            with open(html_path, encoding="utf-8") as fh:
                report_html = fh.read()
            html_col, md_col = st.columns(2)
            html_col.download_button(
                "Download visual report", report_html,
                file_name="aria_findings_report.html", mime="text/html",
                use_container_width=True)
            if os.path.exists(md_path):
                with open(md_path, encoding="utf-8") as fh:
                    md_col.download_button(
                        "Download Markdown", fh.read(),
                        file_name="aria_findings_report.md", mime="text/markdown",
                        use_container_width=True)
            _render_as_iframe(report_html, height=1000, allow_print=True)
        elif os.path.exists(md_path):
            st.info("Generate the visual version with: python -m redteam.report")
            with open(md_path, encoding="utf-8") as fh:
                st.markdown(fh.read())
        else:
            st.info("No report yet. Run python -m redteam.runner --mode both, "
                    "then python -m redteam.report.")
    with review_tab:
        review_path = os.path.join(docs_dir, "code_review.md")
        if os.path.exists(review_path):
            with open(review_path, encoding="utf-8") as fh:
                review = fh.read()
            st.download_button("Download code review", review,
                               file_name="aria_code_review.md", mime="text/markdown")
            st.caption("Source references below identify repository files and tests. "
                       "The downloaded review includes repository links.")
            # Relative repository links do not resolve inside a Streamlit route.
            review_display = re.sub(
                r"\[([^\]]+)\]\((?:\.\./|findings_report\.|architecture\.)[^)]+\)",
                r"`\1`", review)
            st.markdown(review_display)
        else:
            st.info("The source-code review has not been added yet.")


def render_architecture():
    """Render the architecture reference page."""
    st.markdown("## 🏗️ Architecture & Reference")
    st.caption("Review the agent architecture, tools, knowledge base structure, and attack surface.")

    # Look for architecture.html in parent (neobank-hf) or current dir
    html_path = os.path.join(PROJECT_ROOT, "architecture.html")
    if not os.path.exists(html_path):
        st.error("File not found: `architecture.html`")
        return

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    source_path = os.path.join(os.path.dirname(html_path), "docs", "architecture.md")
    if os.path.exists(source_path):
        with open(source_path, encoding="utf-8") as fh:
            st.download_button("Download editable diagrams (Mermaid)", fh.read(),
                               file_name="aria_architecture.md", mime="text/markdown")
    _render_as_iframe(html_content, height=900)


def render_security_guide():
    """Render the AI agent security guide."""
    st.markdown("## 📖 AI Agent Security Guide")
    st.caption("Learn about common AI agent vulnerabilities, attack techniques, and defense strategies.")

    html_path = os.path.join(PROJECT_ROOT, "security_guide.html")
    if not os.path.exists(html_path):
        st.error("File not found: `security_guide.html`")
        return

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    html_content = _apply_guide_dark_mode(html_content)
    _render_as_iframe(html_content, height=900)
