import csv
import io
import json
from pathlib import Path
from typing import List, Tuple

import pandas as pd
import streamlit as st
from openai import OpenAI

st.set_page_config(page_title="Solution Design Assistant", page_icon="🤖", layout="wide")

TEMPLATE_HEADERS = ["block_name", "functionality_description"]
CONFIG_PATH = Path("app_settings.json")
BLOCKS_CACHE_PATH = Path("app_blocks_catalog.csv")


def load_persisted_settings() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_persisted_settings(api_key: str, technical_checks: str) -> None:
    data = {
        "api_key": api_key,
        "technical_checks": technical_checks,
    }
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_cached_blocks() -> List[dict]:
    if not BLOCKS_CACHE_PATH.exists():
        return []
    try:
        df = pd.read_csv(BLOCKS_CACHE_PATH)
    except Exception:
        return []

    if any(col not in df.columns for col in TEMPLATE_HEADERS):
        return []

    return df[TEMPLATE_HEADERS].fillna("").to_dict(orient="records")


def save_uploaded_blocks(uploaded_file) -> List[dict]:
    if uploaded_file is None:
        return []

    raw = uploaded_file.getvalue()
    BLOCKS_CACHE_PATH.write_bytes(raw)

    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:
        st.error(f"Unable to read CSV file: {exc}")
        return []

    missing_cols = [col for col in TEMPLATE_HEADERS if col not in df.columns]
    if missing_cols:
        st.error("CSV file is missing required columns: " + ", ".join(missing_cols))
        return []

    return df[TEMPLATE_HEADERS].fillna("").to_dict(orient="records")


def init_state() -> None:
    persisted = load_persisted_settings()
    defaults = {
        "messages": [],
        "phase": "clarification",
        "api_key": persisted.get("api_key", ""),
        "technical_checks": persisted.get("technical_checks", ""),
        "config_open": False,
        "blocks": load_cached_blocks(),
        "base_request": "",
        "requirement_messages": [],
        "functional_design": "",
        "design_feedback": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def make_template_csv_bytes() -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(TEMPLATE_HEADERS)
    return output.getvalue().encode("utf-8")


def get_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def generate_text(client: OpenAI, prompt: str, temperature: float = 0.2) -> str:
    if hasattr(client, "responses"):
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            temperature=temperature,
        )
        return response.output_text.strip()

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return (completion.choices[0].message.content or "").strip()


def run_clarification_step(
    client: OpenAI,
    technical_checks: str,
    base_request: str,
    requirement_messages: List[str],
) -> Tuple[bool, str]:
    req_history = "\n".join(requirement_messages) if requirement_messages else "(none)"
    prompt = f"""
You are a requirements-clarification assistant.
Language for output: English.

Technical checks provided by admin:
---
{technical_checks or '(none provided)'}
---

User requirement and clarifications so far:
---
{req_history}
---

Main requirement (first user request):
---
{base_request}
---

Task:
1) Evaluate the requirement against the technical checks.
2) If checks are missing, explicitly list which checks are not passed and ask targeted follow-up questions.
3) If checks are complete, confirm all checks are covered and say we'll move to functional design.

Return ONLY valid JSON:
{{
  "complete": true or false,
  "assistant_message": "..."
}}
""".strip()

    text = generate_text(client=client, prompt=prompt, temperature=0.2)
    try:
        parsed = json.loads(text)
        return bool(parsed.get("complete", False)), str(parsed.get("assistant_message", "")).strip()
    except json.JSONDecodeError:
        return False, (
            "Some technical checks are still unclear. "
            "Please provide missing details about architecture, integrations, security, data constraints, and non-functional requirements."
        )


def run_functional_design_step(
    client: OpenAI,
    base_request: str,
    requirement_messages: List[str],
) -> str:
    details = "\n".join(requirement_messages)
    prompt = f"""
You are a functional solution architect.
Language for output: English.

Base requirement:
---
{base_request}
---

Requirement details:
---
{details}
---

Produce a functional system design with:
1) Ordered functional capabilities
2) Logical execution flow
3) Main data/integration touchpoints
4) Assumptions

End with: "If this design looks good, reply CONFIRMED. Otherwise, provide requested changes."
""".strip()
    return generate_text(client=client, prompt=prompt, temperature=0.25)


def run_block_proposal_step(
    client: OpenAI,
    base_request: str,
    requirement_messages: List[str],
    design_feedback: str,
    blocks: List[dict],
) -> str:
    blocks_text = "\n".join(
        f"- {row.get('block_name', '').strip()}: {row.get('functionality_description', '').strip()}"
        for row in blocks
        if row.get("block_name", "").strip()
    )
    if not blocks_text:
        blocks_text = "(No blocks available in CSV.)"

    req_text = "\n".join(requirement_messages)

    prompt = f"""
You are a solution design assistant.
Language for output: English.

Base requirement:
---
{base_request}
---

Refined requirement context:
---
{req_text}
---

User feedback on functional design (or CONFIRMED):
---
{design_feedback}
---

Available blocks from CSV:
---
{blocks_text}
---

Create a proposal with these sections:
1) Final interpreted requirement
2) Recommended blocks from catalog (only relevant ones)
3) Suggested implementation sequence
4) Missing capabilities not covered by listed blocks
5) Optional extra blocks/capabilities to add

If user requested design changes, incorporate them before selecting blocks.
""".strip()

    return generate_text(client=client, prompt=prompt, temperature=0.3)


def reset_chat() -> None:
    st.session_state.messages = []
    st.session_state.phase = "clarification"
    st.session_state.base_request = ""
    st.session_state.requirement_messages = []
    st.session_state.functional_design = ""
    st.session_state.design_feedback = ""


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

            api_key_value = st.text_input(
                "OpenAI API key",
                value=st.session_state.api_key,
                type="password",
                placeholder="sk-...",
                help="Persisted locally in app_settings.json.",
            )
            technical_checks_value = st.text_area(
                "Technical checks to ask the user",
                value=st.session_state.technical_checks,
                height=180,
                placeholder=(
                    "Paste technical checks that must be verified.\n"
                    "Example:\n- expected load\n- retention constraints\n- integrations"
                ),
            )

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Save settings", use_container_width=True):
                    st.session_state.api_key = api_key_value
                    st.session_state.technical_checks = technical_checks_value
                    save_persisted_settings(
                        api_key=st.session_state.api_key,
                        technical_checks=st.session_state.technical_checks,
                    )
                    st.success("Settings saved.")
            with col_b:
                if st.button("Clear saved settings", use_container_width=True):
                    if CONFIG_PATH.exists():
                        CONFIG_PATH.unlink()
                    st.session_state.api_key = ""
                    st.session_state.technical_checks = ""
                    st.success("Saved settings cleared.")

            uploaded_csv = st.file_uploader(
                "Blocks catalog CSV",
                type=["csv"],
                help="Columns required: block_name, functionality_description",
            )
            if uploaded_csv is not None:
                st.session_state.blocks = save_uploaded_blocks(uploaded_csv)
                if st.session_state.blocks:
                    st.success(f"Blocks catalog saved ({len(st.session_state.blocks)} rows).")

            st.download_button(
                "Download empty CSV template",
                data=make_template_csv_bytes(),
                file_name="blocks_template.csv",
                mime="text/csv",
            )

    if st.session_state.blocks:
        st.caption(f"Loaded blocks from catalog: {len(st.session_state.blocks)}")
    else:
        st.caption("No blocks catalog loaded yet.")

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
        warning = "Please open Settings (⚙️), set your OpenAI API key, and save settings."
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
                    st.session_state.requirement_messages.append(user_input)
                    complete, answer = run_clarification_step(
                        client=client,
                        technical_checks=st.session_state.technical_checks,
                        base_request=st.session_state.base_request,
                        requirement_messages=st.session_state.requirement_messages,
                    )
                    st.markdown(answer)
                    st.session_state.messages.append({"role": "assistant", "content": answer})

                    if complete:
                        st.session_state.phase = "functional_design"
                        design = run_functional_design_step(
                            client=client,
                            base_request=st.session_state.base_request,
                            requirement_messages=st.session_state.requirement_messages,
                        )
                        st.session_state.functional_design = design
                        st.markdown("---")
                        st.markdown(design)
                        st.session_state.messages.append({"role": "assistant", "content": design})

                elif st.session_state.phase == "functional_design":
                    st.session_state.design_feedback = user_input
                    st.session_state.phase = "block_proposal"
                    block_proposal = run_block_proposal_step(
                        client=client,
                        base_request=st.session_state.base_request,
                        requirement_messages=st.session_state.requirement_messages,
                        design_feedback=st.session_state.design_feedback,
                        blocks=st.session_state.blocks,
                    )
                    st.markdown(block_proposal)
                    st.session_state.messages.append({"role": "assistant", "content": block_proposal})

                else:
                    st.session_state.requirement_messages.append(user_input)
                    block_proposal = run_block_proposal_step(
                        client=client,
                        base_request=st.session_state.base_request,
                        requirement_messages=st.session_state.requirement_messages,
                        design_feedback=user_input,
                        blocks=st.session_state.blocks,
                    )
                    st.markdown(block_proposal)
                    st.session_state.messages.append({"role": "assistant", "content": block_proposal})
            except Exception as exc:
                err = f"Error while contacting OpenAI API: {exc}"
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": err})

    with st.sidebar:
        st.header("Session")
        if st.button("Reset chat", use_container_width=True):
            reset_chat()
            st.rerun()
        st.caption("Chat history is session-only; settings can be persisted locally.")


if __name__ == "__main__":
    main()
