import csv
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd
from flask import Flask, jsonify, render_template, request, send_file
from openai import OpenAI

app = Flask(__name__)

TEMPLATE_HEADERS = ["block_name", "functionality_description"]
CONFIG_PATH = Path("app_settings.json")
BLOCKS_CACHE_PATH = Path("app_blocks_catalog.csv")
REASONING_MODEL = "o4-mini"
FALLBACK_CHAT_MODEL = "gpt-4o-mini"


def load_persisted_settings() -> Dict[str, str]:
    if not CONFIG_PATH.exists():
        return {"api_key": "", "technical_checks": ""}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return {
            "api_key": data.get("api_key", ""),
            "technical_checks": data.get("technical_checks", ""),
        }
    except Exception:
        return {"api_key": "", "technical_checks": ""}


def save_persisted_settings(api_key: str, technical_checks: str) -> None:
    CONFIG_PATH.write_text(
        json.dumps({"api_key": api_key, "technical_checks": technical_checks}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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


def save_uploaded_blocks(file_storage) -> Tuple[bool, str, List[dict]]:
    raw = file_storage.read()
    BLOCKS_CACHE_PATH.write_bytes(raw)
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:
        return False, f"Unable to read CSV file: {exc}", []

    missing_cols = [col for col in TEMPLATE_HEADERS if col not in df.columns]
    if missing_cols:
        return False, "CSV file is missing required columns: " + ", ".join(missing_cols), []

    return True, "", df[TEMPLATE_HEADERS].fillna("").to_dict(orient="records")


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
            model=REASONING_MODEL,
            input=prompt,
            reasoning={"effort": "medium"},
            temperature=temperature,
        )
        return response.output_text.strip()

    completion = client.chat.completions.create(
        model=FALLBACK_CHAT_MODEL,
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


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/settings")
def get_settings():
    data = load_persisted_settings()
    return jsonify({
        "api_key": data.get("api_key", ""),
        "technical_checks": data.get("technical_checks", ""),
        "blocks_count": len(load_cached_blocks()),
    })


@app.post("/api/settings")
def save_settings_api():
    payload = request.get_json(force=True)
    api_key = str(payload.get("api_key", ""))
    technical_checks = str(payload.get("technical_checks", ""))
    save_persisted_settings(api_key=api_key, technical_checks=technical_checks)
    return jsonify({"ok": True})


@app.post("/api/settings/clear")
def clear_settings_api():
    if CONFIG_PATH.exists():
        CONFIG_PATH.unlink()
    return jsonify({"ok": True})


@app.post("/api/blocks/upload")
def upload_blocks_api():
    file = request.files.get("file")
    if file is None:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400
    ok, error, rows = save_uploaded_blocks(file)
    if not ok:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True, "rows": len(rows)})


@app.get("/api/blocks/template")
def download_template_api():
    data = make_template_csv_bytes()
    return send_file(
        io.BytesIO(data),
        mimetype="text/csv",
        as_attachment=True,
        download_name="blocks_template.csv",
    )


@app.post("/api/chat")
def chat_api():
    payload: Dict[str, Any] = request.get_json(force=True)
    settings = load_persisted_settings()
    api_key = settings.get("api_key", "")
    if not api_key:
        return jsonify({"ok": False, "error": "Please save OpenAI API key in Settings."}), 400

    user_input = str(payload.get("user_input", "")).strip()
    state = payload.get("state", {}) or {}
    phase = state.get("phase", "clarification")
    base_request = state.get("base_request", "")
    requirement_messages = state.get("requirement_messages", [])

    if not user_input:
        return jsonify({"ok": False, "error": "Empty input."}), 400

    if not base_request:
        base_request = user_input

    if not isinstance(requirement_messages, list):
        requirement_messages = []

    client = get_client(api_key)
    technical_checks = settings.get("technical_checks", "")
    blocks = load_cached_blocks()

    try:
        assistant_messages: List[str] = []
        if phase == "clarification":
            # Technical completeness check is asked only once (first interaction).
            requirement_messages.append(user_input)
            _complete, answer = run_clarification_step(
                client=client,
                technical_checks=technical_checks,
                base_request=base_request,
                requirement_messages=requirement_messages,
            )
            assistant_messages.append(answer)
            assistant_messages.append(
                "Please share any additional details now (optional). Then I will produce the functional design in the next response."
            )
            phase = "functional_design"

        elif phase == "functional_design":
            # User can provide missing details (or skip); we then always proceed.
            requirement_messages.append(user_input)
            design = run_functional_design_step(
                client=client,
                base_request=base_request,
                requirement_messages=requirement_messages,
            )
            assistant_messages.append(design)
            phase = "block_proposal"

        else:
            requirement_messages.append(user_input)
            proposal = run_block_proposal_step(
                client=client,
                base_request=base_request,
                requirement_messages=requirement_messages,
                design_feedback=user_input,
                blocks=blocks,
            )
            assistant_messages.append(proposal)

        return jsonify(
            {
                "ok": True,
                "assistant_messages": assistant_messages,
                "state": {
                    "phase": phase,
                    "base_request": base_request,
                    "requirement_messages": requirement_messages,
                },
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Error while contacting OpenAI API: {exc}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
