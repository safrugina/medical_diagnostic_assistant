# AI Medical Diagnostic Assistant (AMDA)

**Version:** 1.5
**Date:** April 2026
**Language:** English / Russian (interface adapts to patient's language)

AMDA is a specialized diagnostic system with a **Streamlit web interface** that implements a strict sequential differential diagnosis protocol with persistent state between sessions. It supports multiple LLM providers (Anthropic Claude, Groq, OpenAI / OpenAI-compatible, Ollama) and includes automated integration with Russian medical information systems (EMIAS, private clinics) for direct data import via browser automation.

> **Important:** This system is an assistive tool only. A final diagnosis and treatment plan can only be provided by a licensed physician. Do not act on any recommendations without first consulting a qualified medical professional in person.

---

## Features

### Streamlit Chat Interface
- **Web-based chat** — interactive multi-turn conversation with the patient via browser
- **Session resume** — on startup, AMDA detects the last saved session and offers to continue from where it left off (resume prompt in the chat itself)
- **Progress indicator** — real-time stage bar showing current diagnostic phase
- **Multi-provider LLM support** — automatically selects Groq, Anthropic Claude, OpenAI / OpenAI-compatible (OpenCode.ai, Together.ai, etc.), or Ollama based on available API keys and the `PROVIDER` env var
- **Header controls** — persistent **🆕 Новая сессия** (archive current case and start fresh) and **🚪 Выйти из системы** (stop the server, session preserved) buttons always visible at the top
- **Auto-scroll** — chat always scrolls to the latest message after stage transitions

### Diagnostic Workflow (16 stages)

| Stage | Name | Description |
|-------|------|-------------|
| 0 | START | Initial greeting / resume offer |
| 1 | CHIEF COMPLAINTS | Primary symptoms, location, intensity, dynamics |
| 2 | COMPLAINT DETAILS | Clarification of chief complaints |
| 3 | ASSOCIATED SYMPTOMS | Present and absent (negative) symptoms |
| 4 | HPI | History of present illness |
| 5 | PAST MEDICAL HISTORY | Chronic conditions, surgeries, allergies, family history |
| 6 | MEDICATIONS | Current medications and supplements |
| 7 | LIFESTYLE | Habits, occupation, physical activity |
| 8 | REVIEW | Summary review and clarifications |
| 9 | COMPLETE | Anamnesis complete → document offer |
| 10 | DOCUMENT ANALYSIS | Scanning and analyzing medical documents |
| 11 | FINISHED | Anamnesis + documents ready → auto-advance |
| 12 | DIFFERENTIAL DIAGNOSIS | Interactive differential diagnosis with probabilities |
| 13 | TEST PRIORITIZATION | Prioritized investigation plan |
| 14 | AWAITING RESULTS | Waiting for new documents (no diagnosis reached the threshold) |
| 15 | FINAL DIAGNOSIS | Final diagnosis reached (threshold met) + case archiving |

### Diagnostic Features
- **Structured anamnesis collection** — chief complaints with full characteristics table (location, intensity, duration, onset, dynamics, triggers, relieving factors)
- **Medical document analysis with OCR** — supports PDF, JPG, PNG, DOCX, FHIR Bundle, SEMD; all parameter names and units are translated to English
- **Document analysis cache** — analyzed documents are cached by filename + modification time; unchanged files are not re-analyzed on subsequent runs
- **Cache error recovery** — on each run, cached entries that contain API error messages (rate limits, HTTP errors) are automatically detected and reprocessed
- **Document age filtering** — each document category (`analyzes/`, `researches/`, `inspections/`) has a configurable max-age threshold; documents older than the limit are excluded from analysis (date extracted from document content, not file metadata)
- **Differential diagnosis** — Bayesian approach, 5–7 diagnoses with ICD-10 codes, probabilities summing to 100%, confidence levels
- **Interactive refinement** — patient can add information at the differential diagnosis stage; probabilities are recalculated with explanation of changes
- **Test prioritization** — minimum necessary investigations for maximum diagnostic value, ordered by priority
- **Red flag detection** — automatic identification of critical symptoms with emergency referral recommendations
- **Configurable diagnosis threshold** — the probability % at which a diagnosis is considered final is set via `DIAGNOSIS_THRESHOLD` in `.env` (default: `90`)
- **Final diagnosis** — issued when the threshold is reached; completed case is archived automatically
- **Iterative loop** — if no diagnosis reaches the threshold, the system waits for new documents and re-runs diagnosis (with iteration counter)

### Data Persistence
- All patient data stored **locally** in `patient-data/` — nothing sent to external servers
- Single session file per patient: `patient-data/sessions/session_{patient_id}.json`
- Structured Markdown patient record: `patient-data/current-patient.md` (updated after each stage)
- Completed cases moved to `patient-data/archive/`
- Diagnostic log: `memory/diagnostic-log.md`

### Data Import & EMR Integration
- **Automated EMIAS import** — direct data extraction from Moscow electronic medical record (lk.emias.mos.ru)
- **Private clinic integration** — Invitro, Helix, Gemotest, Medsi, SberZdorovye laboratories
- **Browser automation** — Playwright-based automated login and document download
- **FHIR Ru Core support** — structured data parsing according to Russian FHIR standards
- **2FA & OTP handling** — automatic management of two-factor authentication codes

---

## Diagnostic Cycle

```
1. Anamnesis collection and structuring (Stages 1–9)
        ↓
2. Medical document analysis (Stage 10, optional)
   [age-filtered by category; error-cached entries reprocessed automatically]
        ↓
3. Differential diagnosis formulation (Stage 12)
        ↓
4. Prioritized plan for additional investigations (Stage 13)
        ↓
5. Iterative refinement (Stage 14 → upload new docs → back to Stage 10)
        ↓
6. [Repeat steps 3–5 until a diagnosis reaches DIAGNOSIS_THRESHOLD (default ≥ 90%)]
        ↓
7. Final diagnosis and recommendations (Stage 15)
```

---

## Project Structure

```
medical_diagnostic_assistant/
├── app.py                               # Streamlit application entry point
├── requirements.txt                     # Python dependencies (Streamlit app)
├── CLAUDE.md                            # Main AMDA protocol (rules for Claude)
├── SPEC.md                              # Technical specifications
├── .python-version                      # Python version pin (3.11)
├── .env                                 # API keys (not committed to git)
│
├── ui/                                  # Streamlit UI modules
│   ├── chat_handler.py                  # LLM calls, prompts, provider detection
│   ├── patient_data_handler.py          # Patient data persistence, document scanning
│   └── anamnesis_manager.py             # Stage machine (16 stages)
│
├── .claude/
│   ├── settings.json                    # Claude Code permissions
│   ├── rules/                           # Clinical rules
│   │   ├── anamnesis.md                 # Anamnesis collection rules
│   │   ├── differential-diagnosis.md    # Differential diagnosis (6 mandatory steps)
│   │   ├── document-analysis.md         # Document analysis + OCR + FHIR + translation
│   │   ├── probability-calculation.md   # Bayesian probability calculation
│   │   ├── test-prioritization.md       # Test prioritization
│   │   ├── red-flags.md                 # Red flags and alarm symptoms
│   │   ├── final-diagnosis.md           # Final diagnosis and recommendations
│   │   ├── patient-data-management.md   # Patient data storage rules
│   │   ├── emr-integration.md           # EMR/EHR integration rules
│   │   ├── data-import.md               # Data import from EMIAS/clinics
│   │   └── ethics-safety.md             # Ethics and safety
│   └── docs/
│       ├── common-lab-reference.md      # Laboratory reference values
│       └── mkb-10-11-mapping.md         # ICD-10 / ICD-11 code mapping
│
├── scripts/                             # Data import automation
│   ├── run-import.py                    # Main launcher (interactive menu)
│   ├── emias_export.py                  # EMIAS export (lk.emias.mos.ru)
│   ├── clinic_export.py                 # Private clinic export
│   ├── utils.py                         # Shared utilities & helpers
│   ├── requirements.txt                 # Import scripts dependencies
│   └── .env.example                     # Environment variables template
│
├── patient-data/
│   ├── current-patient.md               # Current patient record (updated each stage)
│   ├── sessions/                        # Session files: session_{patient_id}.json
│   ├── archive/                         # Completed cases (diagnosis ≥ 90%)
│   └── document-cache.json              # Document analysis cache (by filename + mtime)
│
├── documents/                           # Patient medical documents
│   ├── inspections/                     # Doctor appointments, consultations
│   │   └── emias/                       # From EMIAS import
│   ├── analyzes/                        # Laboratory test results
│   │   └── emias/                       # From EMIAS import
│   ├── researches/                      # Instrumental studies (CT, MRI, ultrasound)
│   │   └── emias/                       # From EMIAS import
│   └── raw/                             # Raw files before categorization
│
└── memory/
    └── diagnostic-log.md                # Stage-by-stage diagnostic log
```

---

## Quick Start

### Step 1: Install Dependencies

```bash
# Python 3.10+ required
pip install -r requirements.txt
```

### Step 2: Configure LLM Provider

Create a `.env` file in the project root (choose one provider):

```env
# Option A: Groq (free tier available — recommended for development)
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile

# Option B: OpenAI or any OpenAI-compatible API (OpenCode.ai, Together.ai, etc.)
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-4o           # model name as shown in the provider's docs
OPENAI_BASE_URL=https://api.openai.com/v1   # change for third-party providers, e.g.:
                                             # https://api.opencode.ai/v1  (OpenCode.ai)
                                             # https://api.together.xyz/v1 (Together.ai)

# Option C: Anthropic Claude
ANTHROPIC_API_KEY=your_anthropic_api_key
ANTHROPIC_MODEL=claude-sonnet-4-6

# Option D: Ollama (local, no API key needed)
OLLAMA_URL=http://localhost:11434/v1
OLLAMA_MODEL=llama3.2
```

Provider is selected automatically: `PROVIDER` env var → `OPENAI_API_KEY` → `GROQ_API_KEY` → `ANTHROPIC_API_KEY` → Ollama.

To force a specific provider regardless of which keys are set, add:
```env
PROVIDER=openai   # or: groq | anthropic | ollama
```

#### Optional parameters

```env
# Probability threshold (%) at which a diagnosis is treated as final (default: 90)
DIAGNOSIS_THRESHOLD=90

# Maximum document age (days) per category — date is read from document content
# analyzes/   — lab results (default: 30 days)
DOC_MAX_DAYS_ANALYSES=30
# researches/ — imaging & diagnostics (default: 730 days = 2 years)
DOC_MAX_DAYS_RESEARCHES=730
# inspections/ — physician visit records (default: 180 days = 6 months)
DOC_MAX_DAYS_INSPECTIONS=180
```

Documents in categories not listed above (e.g., `raw/`) are not age-filtered.
If a document's date cannot be extracted from its content, it is included regardless of age.

### Step 3: (Optional) Import Medical Data

#### From EMIAS (Moscow Electronic Medical Record)
```bash
python scripts/run-import.py --source emias
```

#### From Private Clinics
```bash
python scripts/run-import.py --source invitro
python scripts/run-import.py --source helix
python scripts/run-import.py --source medsi
```

#### From All Configured Sources
```bash
python scripts/run-import.py --source all --period 180
```

You can also manually place documents in the `documents/` folder — AMDA will detect them automatically.

### Step 4: Launch the Application

```bash
streamlit run app.py
```

The app opens in your browser at `http://localhost:8501`.

### Step 5: Follow AMDA's Guidance

1. **On first launch:** if a saved session is found, AMDA will offer to resume it or start a new consultation — choose directly in the chat.
2. **Anamnesis:** answer AMDA's questions about symptoms, history, medications, and lifestyle.
3. **Documents:** after anamnesis is complete, AMDA will scan the `documents/` folder and offer to analyze them.
4. **Diagnosis:** AMDA will generate a differential diagnosis with probabilities and an investigation plan.
5. **Iteration:** upload new test results to `documents/` and press **Repeat diagnostics** to refine the diagnosis.
6. **Final diagnosis:** issued automatically when at least one diagnosis reaches the configured threshold (default ≥ 90%).

---

## LLM Provider Comparison

| Provider | Cost | Speed | Quality | Notes |
|----------|------|-------|---------|-------|
| Groq (Llama 3.3 70B) | Free tier | Very fast | Good | Recommended for development |
| OpenAI GPT-4o | Paid | Fast | Excellent | Strong reasoning, wide availability |
| OpenAI o3 / o4-mini | Paid | Medium | Best | Best for complex diagnostic reasoning |
| Anthropic Claude Sonnet | Paid | Fast | Excellent | Best diagnostic accuracy |
| Anthropic Claude Opus | Paid | Slower | Best | Maximum accuracy |
| Ollama (local) | Free | Depends on hardware | Varies | Full privacy, no internet required |

> **⚠️ Note on Ollama performance:** When using Ollama, response times will be significantly longer compared to cloud providers — depending on your hardware and the model size, each response may take from several seconds to a few minutes. Additionally, the quality of questions and answers may be noticeably lower than with online models (Groq, Anthropic), especially for smaller models (under 14B parameters): responses may be less coherent, contain mixed languages, or miss important clinical nuances. For production use or high diagnostic accuracy, cloud providers are strongly recommended.

---

## Ollama Setup (Local LLM)

Ollama lets you run large language models completely locally — no API key, no internet connection, full data privacy.

### Step 1: Install Ollama

**macOS:**
```bash
brew install ollama
```
Or download the installer from https://ollama.com/download (supports macOS, Linux, Windows).

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows:**
Download and run the `.exe` installer from https://ollama.com/download/windows.

---

### Step 2: Start the Ollama Service

```bash
ollama serve
```

The service starts at `http://localhost:11434`. Keep this terminal open (or configure Ollama to start automatically — see Step 5).

Verify the service is running:
```bash
curl http://localhost:11434
# Expected: "Ollama is running"
```

---

### Step 3: Pull a Model

AMDA works best with instruction-tuned models of **7B parameters or larger**. Recommended options:

| Model | Size | RAM Required | Command |
|-------|------|-------------|---------|
| `llama3.2` | 3B | ~4 GB | `ollama pull llama3.2` |
| `llama3.1:8b` | 8B | ~8 GB | `ollama pull llama3.1:8b` |
| `llama3.1:70b` | 70B | ~48 GB | `ollama pull llama3.1:70b` |
| `mistral` | 7B | ~8 GB | `ollama pull mistral` |
| `qwen2.5:14b` | 14B | ~16 GB | `ollama pull qwen2.5:14b` |
| `gemma3:12b` | 12B | ~12 GB | `ollama pull gemma3:12b` |

> **Recommendation for medical tasks:** use at least a **14B** model for adequate reasoning quality. Models smaller than 7B may produce incomplete or incoherent diagnostic reasoning.

Example:
```bash
ollama pull llama3.1:8b
```

To list downloaded models:
```bash
ollama list
```

---

### Step 4: Configure AMDA to Use Ollama

Add to your `.env` file:

```env
PROVIDER=ollama
OLLAMA_URL=http://localhost:11434/v1
OLLAMA_MODEL=llama3.1:8b
```

If `OLLAMA_MODEL` is not set, AMDA defaults to `llama3.2`.

---

### Step 5: Auto-Start Ollama on System Boot (Optional)

**macOS (launchd):**
```bash
# Ollama installs a launchd service automatically after brew install.
# To start/stop manually:
brew services start ollama
brew services stop ollama
```

**Linux (systemd):**
```bash
sudo systemctl enable ollama
sudo systemctl start ollama
sudo systemctl status ollama
```

**Windows:**
The Ollama Windows installer registers it as a background service that starts automatically.

---

### Step 6: Verify the Setup

```bash
# Test a quick inference
ollama run llama3.1:8b "Hello, are you working?"
```

Then launch AMDA:
```bash
streamlit run app.py
```

The model label in the AMDA header should show **Ollama (local)**.

---

### Hardware Recommendations for Ollama

| Setup | Min RAM | Recommended Model |
|-------|---------|-------------------|
| MacBook / laptop (8 GB RAM) | 8 GB | `llama3.2` (3B) |
| Desktop / workstation (16 GB RAM) | 16 GB | `llama3.1:8b` or `mistral` |
| Workstation with GPU (VRAM ≥ 8 GB) | 16 GB RAM + 8 GB VRAM | `llama3.1:8b` (GPU-accelerated) |
| Server / Mac Studio (32+ GB RAM) | 32 GB | `qwen2.5:14b` or `llama3.1:70b` |

> **GPU acceleration:** Ollama automatically uses the GPU if available (NVIDIA CUDA, AMD ROCm, Apple Metal). No extra configuration is required — install the standard Ollama package.

---

## Patient Data Management

- All data is stored **locally** in the `patient-data/` folder — nothing is sent to external servers.
- For anonymity, use an ID instead of a full name (e.g., `Patient_2026_001`).
- Upon completion of diagnostics, the case is automatically moved to `patient-data/archive/`.
- Document analysis results are cached in `patient-data/document-cache.json` — re-opening an existing session does not re-analyze unchanged files.
- Cached entries that contain API error messages are automatically reprocessed on the next run.
- To start a new consultation (archives current case): click **🆕 Новая сессия** in the header or **🆕 Начать заново** in the chat.
- To stop the server while preserving the current session: click **🚪 Выйти из системы** in the header.
- To delete patient data, remove files from `patient-data/`.

---

## EMR/EHR Integration & Data Import

### Supported Sources

**Russian Medical Systems:**
- **EMIAS** (Moscow) — `lk.emias.mos.ru` — appointments, consultations, lab results, instrumental studies

**Private Clinics & Laboratories:**
- Invitro, Helix, Gemotest, Medsi, SberZdorovye

### Supported Document Formats

| Format | Description | Extraction Method |
|--------|-------------|-------------------|
| PDF (text layer) | Digital documents with embedded text | `pypdf` text extraction |
| PDF (scanned) | Scanned pages without a text layer | `pymupdf` renders pages → Tesseract OCR |
| JPG / PNG | Scans, photos of lab results | Tesseract OCR (`rus+eng`) |
| DOCX | Word documents | `python-docx` paragraph + table extraction |
| FHIR Bundle (JSON) | Structured data per Ru Core | Direct read + LLM parsing |
| SEMD / REMD (XML) | HL7 CDA electronic documents | Direct read + LLM parsing |
| TXT | Plain text exports | Direct UTF-8 read |

OCR output is prefixed with `[OCR]` so the analysis model is aware the source quality may vary.
If Tesseract is not installed, scanned PDFs and images are skipped gracefully with a message in the document cache.

#### Tesseract OCR — system dependency

Tesseract must be installed separately (it is a system binary, not a Python package):

**macOS:**
```bash
brew install tesseract tesseract-lang   # includes Russian (rus) and all other language packs
```

**Ubuntu / Debian:**
```bash
sudo apt install tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng
```

**Windows:**
Download the installer from https://github.com/UB-Mannheim/tesseract/wiki — enable the Russian language pack during installation.

After installing Tesseract, verify with:
```bash
tesseract --version
tesseract --list-langs   # should include: eng, rus
```

### Security & Privacy
- Credentials are **never stored** in the project
- Entered interactively or via secure `.env` file (not committed to git)
- All documents stored **locally only**
- Compliance with Federal Law 152-FZ (Russia's data protection law)

---

## Technical Requirements

### Runtime
- **Python 3.10+** (required for reliable UTF-8 handling with Cyrillic)
- **Streamlit 1.40+**

### Python Dependencies (`requirements.txt`)
```
streamlit==1.40.2       # Web interface
anthropic==0.43.0       # Anthropic Claude API
openai>=1.30.0          # OpenAI-compatible API (Groq, Ollama)
httpx>=0.25.0           # HTTP client with UTF-8 support
pypdf>=4.0.0            # PDF text extraction (text-layer PDFs)
python-dotenv==1.0.1    # .env file loading
markdown>=3.4           # Markdown processing
python-docx>=1.1.0      # DOCX text + table extraction
pymupdf>=1.23.0         # PDF page rendering for scanned PDFs
pytesseract>=0.3.10     # OCR wrapper (requires Tesseract binary — see above)
Pillow>=10.0.0          # Image loading for OCR
```

### System Requirements
- macOS / Linux / Windows with Python 3.10+
- **Tesseract OCR 5.x** with `rus` and `eng` language packs (for scanned PDFs and images — see installation instructions above)
- ~500 MB disk space for patient data, documents, and logs
- Internet connection for cloud LLM providers (Groq, Anthropic)
- For EMIAS/clinic import: Chromium browser (installed by Playwright)

---

## Limitations and Disclaimer

### Medical Limitations
- AMDA **does not replace** a licensed physician and is not a certified medical device.
- The system does not prescribe specific medications or dosages before a confirmed diagnosis reaches the configured threshold (default ≥ 90%).
- When critical symptoms (red flags) are present, the system strongly recommends seeking immediate medical attention.
- Clinical guidelines are based on 2025–2026 standards and should be verified for currency.

### Data Import Limitations
- **EMIAS:** Limited to Moscow (region code 77). Data available only to authorized patients.
- **Private clinics:** Requires valid account and correct credentials. Website structure changes may require script updates.
- **Browser automation:** Subject to site changes; may require periodic maintenance of selectors.
- **Rate limiting:** Some clinics may impose rate limits on automated downloads.

### Known Issues
- OCR accuracy depends on PDF/image quality (recommend ≥ 1000×1000 px for scans)
- Some SEMD/FHIR structures may require format specification updates
- 2FA codes must be entered manually if clinic security blocks automation

