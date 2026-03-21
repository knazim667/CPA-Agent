# CPA-Agent

CPA-Agent is a local-first accounting assistant for macOS that uses Ollama for reasoning, Google Sheets for ledger work, business-specific memory silos, and voice input/output.

## Current Status

The project is scaffolded and the Python files compile successfully.

What works now:
- Main orchestrator with wake-word flow, business switching, custom correction capture, and self-reflection.
- Business-aware memory manager with separate silos for `Business_A` and `Business_B`.
- Google Sheets skill template for reading, writing, and formatting ledger data.
- Google Docs support for creating and appending working-paper notes.
- Local web UI for chat, business switching, browser voice input, and quick links to Sheets and Docs.
- Structured accounting answers in the UI for verified transaction results and account review summaries.
- Learned knowledge memory for Google Sheets and Docs reference material.
- Persona files and memory files are initialized.

What still needs your setup:
- Install dependencies.
- Install and run Ollama locally.
- Pull your target Ollama model.
- Create Google OAuth Desktop App credentials.
  If you do not have any Sheets or Docs yet, CPA-Agent can create them automatically.

## Project Structure

```text
CPA-Agent/
├── core/
│   └── ollama_client.py
├── skills/
│   ├── google_sheets_manager.py
│   ├── payroll_engine.py
│   └── tax_researcher.py
├── memory/
│   ├── short_term.json
│   ├── skill_memory.json
│   ├── active_business.json
│   └── long_term/
│       ├── Business_A/config.json
│       └── Business_B/config.json
├── persona/
│   ├── system_prompt.md
│   └── custom_rules.json
├── main.py
├── memory_manager.py
├── skills.py
└── requirements.txt
```

## How To Run

1. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install Python packages:

```bash
pip install -r requirements.txt
```

3. Install Ollama on your Mac and start it.

4. Pull the model you want to use:

```bash
ollama pull gpt-oss:20b
```

5. Set environment variables:

```bash
export OLLAMA_MODEL="gpt-oss:20b"
export GOOGLE_OAUTH_CLIENT_SECRET_FILE="/absolute/path/to/your-oauth-client.json"
```

6. Authorize once in your browser:

```bash
python3 authorize_google_oauth.py
```

7. Optional bootstrap step to auto-create one Google Sheet and one Google Doc per business:

```bash
python3 bootstrap_google_workspace.py
```

8. Start the agent:

```bash
python3 main.py
```

## Web UI

You can now run CPA-Agent with a local browser interface instead of terminal input.

Start the UI server:

```bash
python3 web_app.py
```

Then open:

```text
http://127.0.0.1:8000
```

The web UI includes:
- Chat interface
- Business switcher
- Browser voice input button
- Optional spoken replies in the browser
- Quick links to the active Google Sheet and Google Doc
- Dashboard cards for transaction volume, income, expenses, and flagged actions
- Structured transaction form for direct ledger posting
- Recent transaction snapshot from the active ledger
- Structured accounting reply cards and verified ledger tables

If the business config has placeholder IDs, the bootstrap script or the agent itself will create:
- a Google Sheet named `<Business Name> CPA Ledger`
- a Google Doc named `<Business Name> CPA Notes`

The created IDs will be written back into the business config files automatically.

## Google Sheets And Docs Access

CPA-Agent now supports both Google Sheets and Google Docs through OAuth2 or a service account JSON key.

If a business has no Sheet or Doc yet, CPA-Agent can create them automatically.

The easiest setup is OAuth2 for a Desktop App. You sign in once in a browser, and the agent reuses the saved token.

## Simple Google Setup

1. Go to Google Cloud Console.
2. Create a new project for CPA-Agent.
3. Enable these APIs:
- Google Sheets API
- Google Drive API
- Google Docs API
4. Go to `Google Auth Platform` and configure the OAuth consent screen.
5. Go to `Clients`.
6. Create a new OAuth client.
7. Choose `Desktop app`.
8. Download the JSON file and keep it on your Mac.
9. Set `GOOGLE_OAUTH_CLIENT_SECRET_FILE` to that file path.
10. Run:

```bash
python3 authorize_google_oauth.py
```

11. A browser window opens. Sign in with the Google account you want CPA-Agent to use.
12. Google saves a reusable token locally in `credentials/google-token.json`.
13. If you do not have any Sheets or Docs yet, run:

```bash
python3 bootstrap_google_workspace.py
```

14. The script will create the assets and save the IDs into the business config files.

Example Sheet URL:

```text
https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit#gid=0
```

The part after `/d/` and before `/edit` is the Sheet ID.

## What You Need To Give Me

You do not need to give me your Google password.

For this agent to connect, you only need:
- A Google OAuth Desktop App JSON file stored locally on your Mac.
- The environment variable `GOOGLE_OAUTH_CLIENT_SECRET_FILE` pointing to that file.

The agent can now create its own Sheets and Docs if none exist.

OAuth2 is the easiest connection path because it uses your own Google account directly.

Service-account auth is still supported as a fallback for automation, but it is no longer the easiest recommended setup.

## Important Notes

- `PyAudio` may need PortAudio installed on macOS. If `pip install` fails, install it with Homebrew:

```bash
brew install portaudio
pip install pyaudio
```

- The code uses macOS `say` for spoken responses.
- The speech flow uses Google speech recognition through the `SpeechRecognition` package.
- The service account email detected from your JSON is `cpa-agent@cpa-agent-490901.iam.gserviceaccount.com`.
- OAuth tokens are stored locally in `credentials/google-token.json`.
- OAuth client secrets should stay local and must not be committed to Git.
- Tax research and payroll logic are templates and still need production-grade rules before you rely on them.
- This is not yet a substitute for final CPA, payroll, or legal review.
