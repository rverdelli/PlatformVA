import csv
import io
import json
from typing import List, Tuple

import pandas as pd
import streamlit as st
from openai import OpenAI

st.set_page_config(page_title="Solution Design Assistant", page_icon="🤖", layout="wide")


TEMPLATE_HEADERS = ["block_name", "functionality_description"]


def init_state() -> None:
    defaults = {
        "messages": [],
        "base_request": "",
        "clarifications": [],
        "phase": "clarification",
        "api_key": "",
        "technical_checks": "",
        "config_open": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def make_template_csv_bytes() -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(TEMPLATE_HEADERS)
    return output.getvalue().encode("utf-8")


def load_blocks_from_upload(uploaded_file) -> List[dict]:
    if uploaded_file is None:
        return []
    try:
        df = pd.read_csv(uploaded_file)
    except Exception as exc:
        st.error(f"Unable to read CSV file: {exc}")
        return []

    missing_cols = [col for col in TEMPLATE_HEADERS if col not in df.columns]
    if missing_cols:
        st.error(
            "CSV file is missing required columns: " + ", ".join(missing_cols)
        )
        return []

    clean_df = df[TEMPLATE_HEADERS].fillna("")
    return clean_df.to_dict(orient="records")


def get_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def run_clarification_step(
    client: OpenAI,
    technical_checks: str,
    base_request: str,
    user_reply: str,
    previous_clarifications: List[str],
) -> Tuple[bool, str]:
    clar_history = "\n".join(previous_clarifications) if previous_clarifications else "(none)"

    prompt = f"""
You are a requirements-clarification assistant.
Language for output: English.

Technical checks provided by admin:
---
{technical_checks or '(none provided)'}
---

Original business request from user:
---
{base_request}
---

Clarification history from user:
---
{clar_history}
---

Latest user message:
---
{user_reply}
---

Task:
1) Verify whether all relevant technical details requested by the technical checks are now covered.
2) If something is missing, ask only the missing clarification questions.
3) If everything is complete, acknowledge completion and say we will generate the solution proposal next.

Return ONLY valid JSON:
{{
  "complete": true or false,
  "assistant_message": "..."
}}
""".strip()

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
        temperature=0.2,
    )
    text = response.output_text.strip()
    try:
        parsed = json.loads(text)
        return bool(parsed.get("complete", False)), str(parsed.get("assistant_message", "")).strip()
    except json.JSONDecodeError:
        return False, (
            "I could not parse the clarification result reliably. "
            "Please provide any missing technical details about architecture, integrations, constraints, and non-functional requirements."
        )


def run_solution_step(
    client: OpenAI,
    technical_checks: str,
    base_request: str,
    clarifications: List[str],
    blocks: List[dict],
) -> str:
    blocks_text = "\n".join(
        [
            f"- {row.get('block_name', '').strip()}: {row.get('functionality_description', '').strip()}"
            for row in blocks
            if row.get("block_name", "").strip()
        ]
    )
    if not blocks_text:
        blocks_text = "(No blocks available in CSV.)"

    clarification_text = "\n".join(clarifications) if clarifications else "(none)"

    prompt = f"""
You are a solution design assistant.
Language for output: English.

Input business request:
---
{base_request}
---

Technical checks used during clarification:
---
{technical_checks or '(none provided)'}
---

Collected user clarifications:
---
{clarification_text}
---

Available blocks from CSV:
---
{blocks_text}
---

Create a practical proposal with these sections:
1) "Summary of requested system"
2) "Recommended blocks from catalog" (select only relevant blocks and explain why)
3) "Suggested implementation flow" (ordered steps)
4) "Missing capabilities not covered by existing blocks"
5) "Optional additional blocks to consider" (if useful)

Be concrete and concise.
""".strip()

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
        temperature=0.3,
    )
    return response.output_text.strip()


def main() -> None:
    init_state()

    top_left, top_right = st.columns([0.92, 0.08])
    with top_left:
        st.title("🤖 Solution Design Chatbot")
    with top_right:
        if st.button("⚙️", help="Settings", use_container_width=True):
            st.session_state.config_open = not st.session_state.config_open

    if st.session_state.config_open:
        with st.container(border=True):
            st.subheader("Settings")
            st.session_state.api_key = st.text_input(
                "OpenAI API key",
                value=st.session_state.api_key,
                type="password",
                placeholder="sk-...",
                help="Stored only in the current browser session.",
            )
            st.session_state.technical_checks = st.text_area(
                "Technical checks to ask the user",
                value=st.session_state.technical_checks,
                height=180,
                placeholder=(
                    "Paste the technical checks that must be verified.\n"
                    "Example:\n"
                    "- expected load\n"
                    "- data retention constraints\n"
                    "- integrations"
                ),
            )

            uploaded_csv = st.file_uploader(
                "Blocks catalog CSV",
                type=["csv"],
                help="Columns required: block_name, functionality_description",
            )
            st.download_button(
                "Download empty CSV template",
                data=make_template_csv_bytes(),
                file_name="blocks_template.csv",
                mime="text/csv",
            )
    else:
        uploaded_csv = None

    if "blocks" not in st.session_state:
        st.session_state.blocks = []
    if uploaded_csv is not None:
        st.session_state.blocks = load_blocks_from_upload(uploaded_csv)

    if st.session_state.blocks:
        st.caption(f"Loaded blocks from CSV: {len(st.session_state.blocks)}")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    user_input = st.chat_input("Describe the system you want to build...")
    if not user_input:
        return

    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    if not st.session_state.api_key:
        warning = "Please open Settings (⚙️) and provide an OpenAI API key first."
        st.session_state.messages.append({"role": "assistant", "content": warning})
        with st.chat_message("assistant"):
            st.markdown(warning)
        return

    client = get_client(st.session_state.api_key)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                if st.session_state.base_request == "":
                    st.session_state.base_request = user_input

                if st.session_state.phase == "clarification":
                    st.session_state.clarifications.append(user_input)
                    complete, answer = run_clarification_step(
                        client=client,
                        technical_checks=st.session_state.technical_checks,
                        base_request=st.session_state.base_request,
                        user_reply=user_input,
                        previous_clarifications=st.session_state.clarifications,
                    )
                    st.markdown(answer)
                    st.session_state.messages.append({"role": "assistant", "content": answer})

                    if complete:
                        st.session_state.phase = "solution"
                        proposal = run_solution_step(
                            client=client,
                            technical_checks=st.session_state.technical_checks,
                            base_request=st.session_state.base_request,
                            clarifications=st.session_state.clarifications,
                            blocks=st.session_state.blocks,
                        )
                        st.markdown("---")
                        st.markdown(proposal)
                        st.session_state.messages.append({"role": "assistant", "content": proposal})
                else:
                    proposal = run_solution_step(
                        client=client,
                        technical_checks=st.session_state.technical_checks,
                        base_request=st.session_state.base_request,
                        clarifications=st.session_state.clarifications + [user_input],
                        blocks=st.session_state.blocks,
                    )
                    st.markdown(proposal)
                    st.session_state.messages.append({"role": "assistant", "content": proposal})
            except Exception as exc:
                err = f"Error while contacting OpenAI API: {exc}"
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": err})

    with st.sidebar:
        st.header("Session")
        if st.button("Reset chat", use_container_width=True):
            for key in ["messages", "base_request", "clarifications", "phase"]:
                if key == "messages":
                    st.session_state[key] = []
                elif key == "clarifications":
                    st.session_state[key] = []
                elif key == "phase":
                    st.session_state[key] = "clarification"
                else:
                    st.session_state[key] = ""
            st.rerun()
        st.caption("Conversation is temporary and stored only for this browser session.")


if __name__ == "__main__":
    main()
