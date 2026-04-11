# AI Medical Diagnostic Assistant (AMDA)

**Version:** 1.2
**Date:** April 11, 2026
**Language:** English (default)

AMDA is a specialized diagnostic system built on Claude Code that implements a strict sequential differential diagnosis protocol with persistent state between sessions.

> **Important:** This system is an assistive tool only. A final diagnosis and treatment plan can only be provided by a licensed physician. Do not act on any recommendations without first consulting a qualified medical professional in person.

---

## Features

- **Structured anamnesis collection** — chief complaints, illness history, life history, lifestyle habits
- **Medical document analysis with OCR** — supports PDF, JPG, PNG, DOCX with automatic text recognition
- **Differential diagnosis** — Bayesian approach, diagnosis list with probabilities (sum = 100%)
- **Test prioritization** — minimum necessary set of investigations for maximum diagnostic value
- **Red flag detection** — automatic identification of critical symptoms with emergency referral recommendations
- **Stateful mode** — all patient data is saved in project files and persists between sessions
- **Final diagnosis** — issued only when at least one diagnosis reaches ≥ 90% probability

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
├── .claude/
│   ├── settings.json                # Claude Code permissions
│   ├── rules/                       # Clinical rules
│   │   ├── anamnesis.md             # Anamnesis collection rules
│   │   ├── differential-diagnosis.md # Differential diagnosis
│   │   ├── document-analysis.md     # Document analysis + OCR
│   │   ├── probability-calculation.md # Probability calculation (Bayes)
│   │   ├── test-prioritization.md   # Test prioritization
│   │   ├── red-flags.md             # Red flags and alarm symptoms
│   │   ├── final-diagnosis.md       # Final diagnosis and recommendations
│   │   ├── patient-data-management.md # Patient data storage
│   │   └── ethics-safety.md         # Ethics and safety
│   └── docs/                        # Reference documentation
│       ├── architecture.md          # System architecture
│       ├── common-lab-reference.md  # Laboratory reference values
│       └── mkb-10-11-mapping.md     # ICD-10 / ICD-11 code mapping
├── patient-data/
│   ├── current-patient.md           # Current patient (updated at each stage)
│   ├── sessions/                    # Session history by date
│   └── archive/                     # Completed cases (diagnosis ≥ 90%)
└── documents/                       # Patient medical documents for upload
```

---

## Quick Start

1. Open the project in Claude Code:
   ```bash
   cd medical_diagnostic_assistant
   claude
   ```

2. The system will automatically greet the patient and begin anamnesis collection.

3. To upload medical documents (lab results, imaging, discharge summaries), place files in the `documents/` folder and notify the system.

4. Follow AMDA's instructions — the system will guide you through all diagnostic stages.

---

## Patient Data Management

- All data is stored **locally** in the `patient-data/` folder — nothing is sent to external servers.
- For anonymity, it is recommended to use an ID instead of a full name (e.g., `Patient_2026_001`).
- Upon completion of diagnostics, the case is automatically moved to `patient-data/archive/`.
- To delete patient data, remove the corresponding files from `patient-data/`.

---

## Technical Requirements

- [Claude Code](https://claude.ai/code) (CLI)
- Model: `claude-sonnet-4-6` or higher (recommended: `claude-opus-4-6` for best diagnostic accuracy)

---

## Limitations and Disclaimer

- AMDA **does not replace** a licensed physician and is not a medical device.
- The system does not prescribe specific medications or dosages before a confirmed diagnosis of ≥ 90% and without a physician's recommendation.
- When critical symptoms (red flags) are present, the system strongly recommends seeking immediate medical attention.
- Clinical guidelines in the system are based on 2025–2026 standards and should be verified for currency before use.
