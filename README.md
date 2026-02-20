# Solution Design Chatbot (Python)

A web chatbot (Flask + vanilla JS/CSS) that helps transform a business request into a solution proposal.

## Features

- Non-Streamlit frontend with a cleaner UI and chat layout.
- **⚙️ Settings** modal with:
  - OpenAI API key
  - Technical checks text
  - Blocks catalog CSV upload
- Persistent settings in `app_settings.json`.
- Persistent blocks catalog in `app_blocks_catalog.csv`.
- LLM generation uses a reasoning model (`o4-mini`) when available, with backward-compatible fallback.
- Workflow:
  1. Clarification checks against configured technical checks.
  2. Functional system design proposal.
  3. Block recommendation proposal based on user confirmation or requested changes.
- Chat history persists only in browser tab session (`sessionStorage`).

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open `http://localhost:8000`.

## CSV format

Required columns:

- `block_name`
- `functionality_description`

A starter template is included as `blocks_template.csv` and can also be downloaded from the UI.
