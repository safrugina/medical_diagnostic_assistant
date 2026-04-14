# Patient Data Storage Rules (AMDA)

**Version:** 1.1 (April 2026)

## Core Principle
All patient data and intermediate diagnostic results are stored **exclusively in project files** in the `patient-data/` folder.  
This ensures full statefulness and compliance with security requirements.

## Mandatory Agent Actions

1. **At the start of a new session**  
   - Read `patient-data/current-patient.md`.  
   - If the file is missing — create it from the template.

2. **After each significant stage** (anamnesis, document analysis, probability recalculation, etc.):
   - Update `patient-data/current-patient.md`.
   - Create or append a session file in `patient-data/sessions/`.
   - Briefly update `memory/diagnostic-log.md`.

3. **When working with EMR data**  
   - Always specify the data source in `current-patient.md` (FHIR Ru Core, SEMD, MIS export, etc.).
   - Save original files in `./documents/` with descriptive names.

4. **Upon reaching the final diagnosis**  
   - Move the completed case to `patient-data/archive/`.
   - Prepare `current-patient.md` for a new patient.

5. **When importing data from EMIAS / clinics**
   - Automatically update the current-patient.md section "Downloaded Documents"
   - Mark the source ("EMIAS", "Invitro", "Medsi", etc.)

## Storage Format
- Use only Markdown with clear headings and tables.
- It is recommended to use an anonymized patient ID (Patient_2026_001).
- Never store sensitive data in plain text without user consent.

→ Detailed EMR integration rules: `@.claude/rules/emr-integration.md`
