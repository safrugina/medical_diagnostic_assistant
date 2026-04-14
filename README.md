# AI Medical Diagnostic Assistant (AMDA)

**Version:** 1.3
**Date:** April 15, 2026
**Language:** English (default)

AMDA is a specialized diagnostic system built on Claude Code that implements a strict sequential differential diagnosis protocol with persistent state between sessions. It includes automated integration with Russian medical information systems (EMIAS, private clinics) for direct data import via browser automation.

> **Important:** This system is an assistive tool only. A final diagnosis and treatment plan can only be provided by a licensed physician. Do not act on any recommendations without first consulting a qualified medical professional in person.

---

## Features

### Diagnostic System
- **Structured anamnesis collection** — chief complaints, illness history, life history, lifestyle habits
- **Medical document analysis with OCR** — supports PDF, JPG, PNG, DOCX, FHIR Bundle, SEMD with automatic text recognition
- **Differential diagnosis** — Bayesian approach, diagnosis list with probabilities (sum = 100%)
- **Test prioritization** — minimum necessary set of investigations for maximum diagnostic value
- **Red flag detection** — automatic identification of critical symptoms with emergency referral recommendations
- **Stateful mode** — all patient data is saved in project files and persists between sessions
- **Final diagnosis** — issued only when at least one diagnosis reaches ≥ 90% probability

### Data Import & EMR Integration
- **Automated EMIAS import** — direct data extraction from Moscow electronic medical record (lk.emias.mos.ru)
- **Private clinic integration** — Invitro, Helix, Gemotest, Medsi, SberZdorovye laboratories
- **Browser automation** — Playwright-based automated login and document download
- **FHIR Ru Core support** — structured data parsing according to Russian FHIR standards
- **2FA & OTP handling** — automatic management of two-factor authentication codes
- **Batch import** — import from multiple sources in one run

---

## Diagnostic Cycle

```
1. Anamnesis collection and structuring
        ↓
2. Medical document analysis (if documents are provided)
        ↓
3. Differential diagnosis formulation
        ↓
4. Prioritized plan for additional investigations
        ↓
5. Iterative refinement (as new data is received)
        ↓
6. [Repeat steps 3–5 until at least one diagnosis reaches ≥ 90%]
        ↓
7. Final diagnosis and recommendations
```

---

## Project Structure

```
medical_diagnostic_assistant/
├── CLAUDE.md                        # Main AMDA protocol
├── SPEC.md                          # Technical specifications
├── .claude/
│   ├── settings.json                # Claude Code permissions
│   ├── rules/                       # Clinical rules (English)
│   │   ├── anamnesis.md             # Anamnesis collection rules
│   │   ├── differential-diagnosis.md # Differential diagnosis
│   │   ├── document-analysis.md     # Document analysis + OCR + FHIR
│   │   ├── probability-calculation.md # Probability calculation (Bayes)
│   │   ├── test-prioritization.md   # Test prioritization
│   │   ├── red-flags.md             # Red flags and alarm symptoms
│   │   ├── final-diagnosis.md       # Final diagnosis and recommendations
│   │   ├── patient-data-management.md # Patient data storage
│   │   ├── emr-integration.md       # EMR/EHR integration rules
│   │   ├── data-import.md           # Data import from EMIAS/clinics
│   │   └── ethics-safety.md         # Ethics and safety
│   └── docs/
│       ├── common-lab-reference.md  # Laboratory reference values
│       └── mkb-10-11-mapping.md     # ICD-10 / ICD-11 code mapping
├── scripts/                         # Data import automation
│   ├── run-import.py                # Main launcher (interactive menu)
│   ├── emias_export.py              # EMIAS export (lk.emias.mos.ru)
│   ├── clinic_export.py             # Private clinic export
│   ├── utils.py                     # Shared utilities & helpers
│   ├── requirements.txt             # Python dependencies
│   └── .env.example                 # Environment variables template
├── patient-data/
│   ├── current-patient.md           # Current patient (updated at each stage)
│   ├── sessions/                    # Session history by date
│   ├── archive/                     # Completed cases (diagnosis ≥ 90%)
│   └── diagnostic-log.md            # Import/analysis log
├── documents/                       # Patient medical documents
│   ├── inspections/                 # Doctor appointments, consultations
│   │   └── emias/                   # From EMIAS import
│   ├── analyzes/                    # Laboratory test results
│   │   └── emias/                   # From EMIAS import
│   ├── researches/                  # Instrumental studies (CT, MRI, ultrasound)
│   │   └── emias/                   # From EMIAS import
│   └── raw/                         # Raw files before categorization
└── logs/
    └── import-log.txt               # Import script logs
```

---

## Quick Start

### Step 1: Install Dependencies
```bash
cd medical_diagnostic_assistant/scripts
pip install -r requirements.txt
```

### Step 2: Import Medical Data (Optional)

#### From EMIAS (Moscow Electronic Medical Record)
```bash
python run-import.py --source emias
```
or interactively:
```bash
python run-import.py
```

#### From Private Clinics
```bash
python run-import.py --source invitro
python run-import.py --source helix
python run-import.py --source medsi
python run-import.py --source sberhealth
```

#### From All Configured Sources
```bash
python run-import.py --source all --period 180
```

Credentials can be provided via:
- `.env` file in `scripts/` folder (see `scripts/.env.example`)
- Interactive prompt during script execution

### Step 3: Start Diagnostic Session
```bash
cd ..
claude
```

### Step 4: Follow AMDA's Guidance
1. The system will greet you and begin anamnesis collection.
2. Provide information about symptoms, medical history, medications.
3. AMDA will analyze any imported documents and perform OCR/FHIR parsing.
4. The system will generate a differential diagnosis and prioritize additional tests.
5. Follow AMDA's instructions until a diagnosis reaches ≥ 90% confidence.

---

## Patient Data Management

- All data is stored **locally** in the `patient-data/` folder — nothing is sent to external servers.
- For anonymity, it is recommended to use an ID instead of a full name (e.g., `Patient_2026_001`).
- Upon completion of diagnostics, the case is automatically moved to `patient-data/archive/`.
- To delete patient data, remove the corresponding files from `patient-data/`.

---

## EMR/EHR Integration & Data Import

### Supported Sources

**Russian Medical Systems:**
- **EMIAS** (Moscow) — Personal account: https://lk.emias.mos.ru/
  - Appointments, consultations, lab results, instrumental studies
  - Authentication via ESIA (Gosuslugi)

**Private Clinics & Laboratories:**
- **Invitro** — https://invitro.ru/lk/
- **Helix** — https://helix.ru/lk
- **Gemotest** — https://gemotest.ru
- **Medsi** — https://medsi.ru/personal/
- **SberZdorovye** — https://sberzdorovye.ru

### Data Import Workflow

1. **Run import script:**
   ```bash
   python scripts/run-import.py
   ```

2. **Select data source** and date range (default: 180 days)

3. **Automated download:**
   - Browser automation with Playwright
   - Handles 2FA/OTP authentication
   - Downloads documents to `documents/` folders

4. **Automatic categorization:**
   - Inspections → `documents/inspections/emias/`
   - Laboratory analyzes → `documents/analyzes/emias/`
   - Instrumental researches → `documents/researches/emias/`

5. **Integration with AMDA:**
   - Ask AMDA to analyze new documents
   - System performs OCR + FHIR parsing
   - Updates `patient-data/current-patient.md`

### Supported Formats
- **PDF** — primary format for all documents
- **FHIR Bundle (JSON)** — structured data per Ru Core
- **SEMD / REMD** — structured electronic medical documents (HL7 CDA XML)
- **Images (JPG/PNG)** — with automatic OCR recognition

### Security & Privacy
- Credentials are **never stored** in the project
- Entered interactively or via secure `.env` file (not committed to git)
- All documents stored **locally only**
- Compliance with Federal Law 152-FZ (Russia's data protection law)

---

## Technical Requirements

### Claude Code
- [Claude Code](https://claude.ai/code) (CLI) — latest version
- Model: `claude-sonnet-4-6` or higher
  - Recommended: `claude-opus-4-6` for best diagnostic accuracy
  - Haiku 4.5 can be used for lightweight tasks (code translation, preprocessing)

### Python & Dependencies
- Python 3.9+
- Required packages (see `scripts/requirements.txt`):
  - `playwright` — browser automation for data import
  - `loguru` — structured logging
  - `python-dotenv` — environment variable management
  - `rich` — formatted console output
  - `tqdm` — progress bars
  - Additional: `pdf2image`, `pytesseract` for OCR (optional)

### System Requirements
- macOS / Linux / Windows with Python 3.9+
- ~500 MB disk space for patient data and logs
- Internet connection for EMIAS/clinic login (import phase)
- Browsers: Chromium (installed by Playwright)

---

## Limitations and Disclaimer

### Medical Limitations
- AMDA **does not replace** a licensed physician and is not a certified medical device.
- The system does not prescribe specific medications or dosages before a confirmed diagnosis of ≥ 90% and without a physician's recommendation.
- When critical symptoms (red flags) are present, the system strongly recommends seeking immediate medical attention.
- Clinical guidelines in the system are based on 2025–2026 standards and should be verified for currency before use.

### Data Import Limitations
- **EMIAS:** Limited to Moscow (region code 77). Data available only to authorized patients.
- **Private clinics:** Requires valid account and correct credentials. Website structure changes may require updates.
- **Browser automation:** Subject to site changes, may require periodic maintenance of selectors.
- **Compatibility:** Data format compatibility depends on clinic's current FHIR Ru Core implementation status.
- **Rate limiting:** Some clinics may impose rate limits on automated downloads.

### Known Issues
- OCR accuracy depends on PDF/image quality (recommend 1000×1000 px minimum for scans)
- Some SEMD/FHIR structures may require format specification updates
- 2FA codes must be entered manually if automation is blocked by clinic security

---

## Recent Updates (v1.3)

- ✅ Automated EMIAS data import with browser automation
- ✅ Support for 5 major Russian private clinics & laboratories
- ✅ FHIR Ru Core parsing and mapping
- ✅ Automatic document categorization (inspections, analyzes, researches)
- ✅ 2FA/OTP handling for secure login
- ✅ Batch import from multiple sources
- ✅ Interactive import menu with progress tracking
