# Solution Design Chatbot (Python)

A simple Streamlit chatbot that:

1. Collects a business request.
2. Uses configurable **technical checks** to ask for missing details.
3. Generates a solution proposal using a CSV catalog of reusable functional blocks.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## How to use

- Click the **⚙️ Settings** button (top-right).
- Add your **OpenAI API key**.
- Paste your **Technical checks to ask the user**.
- Upload a blocks CSV file (or download and fill the provided template).
- Start chatting in English.

## CSV format

Required columns:

- `block_name`
- `functionality_description`

A starter template is included as `blocks_template.csv`.

## Notes

- Conversation memory is session-only (no persistent history).
- API key is kept only in the active browser session.
