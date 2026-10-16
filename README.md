# Cashback Clarity AI

Understand the offer. Know the conditions. Estimate your cashback.

A local-first Streamlit application that analyzes cashback terms with a local
Ollama/Gemma model, checks explicit conditions deterministically, estimates
cashback with decimal arithmetic, and stores offers and user-managed
investigations in SQLite. It does not initiate payments or contact providers.

## Features

- Dashboard counts and activity from the local database; estimates are never
  presented as money received.
- Analyze pasted offer text or PNG/JPEG screenshots using optional local OCR.
- Review and edit extracted JSON facts before using them.
- Before You Pay checker for offer conditions, transaction eligibility,
  estimated cashback, effective cost, and unresolved mandatory rules.
- Independent percentage/fixed cashback calculator; missing rates are not
  invented and a missing cap is not treated as zero.
- Search, edit, reanalyze, and delete saved offers; status is unknown until
  you or known dates establish it.
- Create, update, and delete missing-cashback investigations, save optional
  local evidence, and prepare a support-message draft.
- Local-only AI requests, database, and screenshots. No cloud AI API is used.

## Architecture

- `main.py`: Streamlit pages and workflows.
- `tools.py`: Decimal calculator and deterministic eligibility rules.
- `model.py`: Ollama availability, dynamic `SKILLS.md` loading, structured
  response parsing, and normalization.
- `database.py`: parameterized SQLite operations and evidence deletion.
- `ocr_utils.py`: local image validation and Tesseract OCR.
- `SKILLS.md`: instructions loaded at runtime and sent with offer text to the
  local model. The loader also checks `skills.md` on case-sensitive systems.
- `tests/`: pytest checks for calculations, eligibility, AI parsing, OCR
  validation, database operations, and app startup.

## Install and run locally on Windows

Open PowerShell in this project folder. Use an existing virtual environment if
you have one, or create one:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The app's calculator, saved offers, and tracker do not require Ollama. To use
local AI, install Ollama separately, then verify its executable and model:

```powershell
ollama --version
ollama list
ollama run gemma4:e2b
```

`gemma4:e2b` is the default configured name. Check that the exact model is
available in your Ollama installation before downloading anything. Model
downloads can be large; the application never downloads a model for you. If
Ollama uses a non-default endpoint/model, set `OLLAMA_HOST` and `OLLAMA_MODEL`.

Start the application:

```powershell
python -m streamlit run main.py
```

Open **http://localhost:8501** (or **http://127.0.0.1:8501**) in a browser.
The Streamlit server is bound to the local machine by default.

## OCR on Windows

Image preview and validation use Pillow. OCR also requires the Tesseract
executable installed on Windows and available on `PATH`, in addition to the
Python `pytesseract` package installed from `requirements.txt`. Restart the
terminal after installing Tesseract. If it is unavailable, the app displays
setup guidance and continues to support pasted/edited text. Screenshots must
be valid PNG/JPEG files no larger than 5 MB.

## Tests

```powershell
python -m pytest -q
```

All Ollama tests use a mock; the suite does not need a running model or make
network AI calls.

## Storage and privacy

- SQLite database: `cashback.db` in this project folder by default.
- Investigation evidence: `uploads/evidence/` in this project folder.
- Set `CASHBACK_DB_PATH` or `CASHBACK_EVIDENCE_DIR` to use another local path.
- Local files are not encrypted by this application. Protect your Windows
  account/device and delete records/evidence when no longer needed.
- Never enter passwords, PINs, OTPs, CVVs, or full payment-card numbers.
- Offer text and screenshots stay on this computer when running locally.
- The local Ollama runtime is checked before analysis; failures are shown in
  the UI and do not fabricate analysis.

## Public deployment

The app is local-first. Opening `localhost` does not create a public URL. The
included Docker configuration is compatible with platforms that run Docker
containers (the previous README described Hugging Face Spaces), but a hosted
deployment needs your own hosting account, repository permissions, and
platform configuration. No deployment URL or hosting account is provisioned
by this project.

To build and run the container locally:

```powershell
docker build -t cashback-clarity .
docker run --rm -p 7860:7860 -v cashback-data:/app/data cashback-clarity
```

The container starts Ollama but does **not** download Gemma by default. To
intentionally download the configured model inside the container, set
`OLLAMA_PULL_MODEL=true` and verify model availability, disk, memory, and
platform limits first. Model download/runtime resource requirements can make
free public hosting unsuitable. A hosted application processes the data on
that hosting provider's infrastructure; do not submit sensitive offer or
investigation details to an untrusted host. Free-container databases may be
ephemeral unless you configure persistent storage.

For a temporary public URL to a local app, use a trusted tunnel provider only
after reviewing its privacy/security terms; that exposes your local server to
the internet. The application itself does not create a tunnel.

## Limitations

- AI-extracted terms can be wrong; inspect the original offer and edit the
  extracted facts.
- Eligibility is based only on explicit rules and details you provide. It is
  not official approval, and unknown mandatory rules remain unresolved.
- Offer dates are displayed as extracted text, not independently verified.
- OCR accuracy depends on image quality and installed Tesseract language data.
- Investigations and support messages are local drafts; the app never submits
  a complaint or confirms cashback with a provider.
