# Patient Data Storage Rules (AMDA)

## Core Principle
All patient data and intermediate diagnostic results are stored **exclusively in project files** within the `patient-data/` folder.
This ensures full statefulness between sessions.

## Mandatory Agent Actions

1. **At the start of a new session**
   - Read `patient-data/current-patient.md` in full.
   - If the file does not exist — create it using the template.

2. **After each cycle stage** (anamnesis, document analysis, diagnosis formulation, probability recalculation):
   - Update `patient-data/current-patient.md` (structured sections 1–7).
   - Create or append a session file with the current date/time in `patient-data/sessions/`.
   - Briefly update `memory/diagnostic-log.md`.

3. **Upon reaching a final diagnosis (≥ 90%)**
   - Move the current file to `patient-data/archive/` with the final version.
   - Clear `current-patient.md` or prepare a template for the next patient.

## Storage Format
- Use only Markdown with clear headings and tables.
- Never store sensitive data (full name, passport details) in plain text without user consent. Recommend using an anonymized ID (Patient_2026_001).
- Always preserve change history — do not overwrite old sessions.

## Security and Privacy
- Remind the user that data is stored locally on their computer.
- Do not upload patient data to external services.
- If the user requests data deletion — remove the files from `patient-data/`.

This rule has the highest priority. Never skip updating `current-patient.md`.
