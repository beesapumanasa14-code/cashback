---
title: Cashback Clarity AI
sdk: docker
app_port: 7860
---

# Cashback Clarity AI

Understand the offer. Know the conditions. Estimate your cashback.

A Streamlit application that analyzes cashback terms with a local Ollama/Gemma
model, checks explicit conditions deterministically, estimates cashback with
decimal arithmetic, and stores offers and user-managed investigations in
SQLite. It does not initiate payments or contact providers.

## Features

- Real dashboard counts and recent activity from SQLite.
- Analyze pasted text or PNG/JPEG screenshots with optional local OCR.
- Review and edit extracted JSON facts before using them.
- Before You Pay checks eligibility, estimates cashback/effective cost, and
  identifies unresolved mandatory rules.
- Independent percentage/fixed cashback calculator. Missing rates are not
  invented; a missing cap is not treated as zero.
- Search, edit, reanalyze, and delete saved offers.
- Create, update, and delete missing-cashback investigations; save local
  evidence and prepare a support-message draft.
- User accounts with salted PBKDF2-SHA256 password hashes; offers,
  calculations, investigations, and evidence are scoped to the signed-in user.

## Architecture

- `main.py`: Streamlit interface, account sign-in, and workflows.
- `tools.py`: Decimal calculator, date parsing, and deterministic eligibility.
- `model.py`: Ollama availability, dynamic `SKILLS.md` loading, structured
  response parsing, and validation.
- `database.py`: account/password operations, scoped SQLite persistence, and
  evidence deletion.
- `ocr_utils.py`: local image validation and Tesseract OCR.
- `SKILLS.md`: rules loaded at runtime and sent with offer text to Gemma. The
  loader also checks `skills.md` on case-sensitive systems.
- `tests/`: pytest coverage for calculations, eligibility, model parsing,
  database/account isolation, screenshot validation, and app startup.

## Run locally on Windows

Open PowerShell in this project folder. Reuse an existing virtual environment
or create one:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Launch Ollama separately to use AI. Verify the exact model before downloading:

```powershell
ollama --version
ollama list
ollama run gemma4:e2b
```

Model downloads can be large; the application never downloads one
automatically. If Ollama uses another endpoint/model, set `OLLAMA_HOST` and
`OLLAMA_MODEL`.

Run the application:

```powershell
python -m streamlit run main.py
```

Open **http://localhost:8501** or **http://127.0.0.1:8501**. Create a
username (3–32 letters/numbers/dot/underscore/hyphen) and a unique password
of at least 12 characters. Passwords are not recoverable by email; there is
no password-reset service. Do not reuse a banking, payment, or email password.

## OCR on Windows

Pillow validates and previews images. OCR also needs the Tesseract executable
installed on Windows and available on `PATH`, plus `pytesseract` from
`requirements.txt`. Restart the terminal after installing Tesseract. If it is
unavailable, the app gives setup guidance and manual text input remains
available. Screenshots must be PNG/JPEG and at most 5 MB.

## Tests

```powershell
python -m pytest -q
```

Ollama is mocked in unit tests; tests do not require a model or network AI call.

## Storage and privacy

- SQLite: `cashback.db` in the project folder by default.
- Evidence: `uploads/evidence/` in the project folder.
- Override locations with `CASHBACK_DB_PATH` and `CASHBACK_EVIDENCE_DIR`.
- User passwords are stored as salted PBKDF2 hashes, never plaintext.
- All user records are scoped to the signed-in account. Sign-out clears
  Streamlit session state; account deletion removes that user's records and
  evidence.
- Local SQLite/evidence are not encrypted at rest. Protect your device and
  delete records when no longer needed.
- Never enter payment passwords, PINs, OTPs, CVVs, or complete card numbers.
- The local Ollama runtime is checked before analysis; errors do not generate
  fabricated analysis.

## Public deployment (Streamlit Community Cloud)

The source repository is published at
https://github.com/beesapumanasa14-code/cashback. For free Streamlit Community
Cloud hosting:

1. Sign in to https://share.streamlit.io/ with the GitHub account that can
   access the repository.
2. Create an app from `beesapumanasa14-code/cashback`, branch `main`, file
   `main.py`, or start at the
   [pre-filled deployment page](https://share.streamlit.io/deploy?repository=beesapumanasa14-code/cashback&branch=main&mainModule=main.py).
3. In the app's **Settings → Secrets**, set:

   ```toml
   HOSTED_PUBLIC = "true"
   ```

4. Deploy and wait for the first build. The public URL is assigned by
   Streamlit after the app starts.

This deployment runs the app without a local Ollama server or Gemma model.
Sign-in, calculations, saved offers, and investigations work; AI analysis
will show a clear Ollama-unavailable message. Connecting `OLLAMA_HOST` to
another server requires a separately hosted, trusted Ollama service with
`gemma4:e2b`, network access, and appropriate security. Keep that endpoint
private; do not expose Ollama directly to the internet.

**Public hosting is not local-only.** Offer text, screenshots, account data,
and investigations are processed and stored on the hosting provider's
infrastructure. User accounts separate app records, but the app does not
encrypt the SQLite database or evidence at rest. Free hosted filesystems may
be ephemeral and reset on restart/redeploy. Do not enter sensitive information
or use a password from another service. The sign-in page displays this notice.

The repository also includes a Docker configuration for other platforms. The
container does not download Gemma by default. The configured `gemma4:e2b`
model on the development machine occupies about 4.6 GB; confirm a host's disk,
memory, and storage limits before enabling `OLLAMA_PULL_MODEL=true`.

To build/run the Docker container locally:

```powershell
docker build -t cashback-clarity .
docker run --rm -p 7860:7860 -v cashback-data:/app/data cashback-clarity
```

The app does not create a public URL or a tunnel automatically. Streamlit
Community Cloud assigns a URL only after you authorize GitHub access and
successfully create the hosted app.

## Limitations

- AI-extracted conditions can be wrong; inspect the original offer and edit
  the extracted facts.
- Eligibility is based only on explicit rules and user input; it is not
  provider confirmation.
- Dates are shown as extracted and are not independently verified.
- OCR accuracy depends on image quality and Tesseract language data.
- Investigations and support messages are user-managed drafts. The app does
  not contact a provider or submit a complaint.
