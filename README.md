# Solution Design Chatbot (Python)

A Streamlit chatbot that helps transform a business request into a solution proposal.

## Features

- Session chat with in-page conversation history.
- **⚙️ Settings** panel (top-right) with:
  - OpenAI API key
  - Technical checks text
  - Blocks catalog CSV upload
- **Persistent settings** saved locally (`app_settings.json`).
- **Persistent blocks catalog** saved locally (`app_blocks_catalog.csv`) after upload.
- LLM generation uses a **reasoning model** (`o4-mini`) when available, with backward-compatible fallback.
- Two-step assistant workflow + final proposal:
  1. Clarification checks against configured technical checks.
  2. Functional system design proposal.
  3. Block recommendation proposal based on user confirmation or requested changes.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## CSV format

Required columns:

- `block_name`
- `functionality_description`

A starter template is included as `blocks_template.csv`.

## Notes

- Chat history remains session-only and resets when the app session ends.
- Settings and blocks catalog are persisted on disk for reuse.
